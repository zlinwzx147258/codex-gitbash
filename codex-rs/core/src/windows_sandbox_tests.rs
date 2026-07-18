use super::*;
use codex_config::types::WindowsAgentShellToml;
use codex_config::types::WindowsToml;
use codex_features::Features;
use codex_features::FeaturesToml;
use pretty_assertions::assert_eq;
use std::collections::BTreeMap;

#[test]
fn elevated_flag_works_by_itself() {
    let mut features = Features::with_defaults();
    features.enable(Feature::WindowsSandboxElevated);

    assert_eq!(
        WindowsSandboxLevel::from_features(&features),
        WindowsSandboxLevel::Elevated
    );
}

#[test]
fn restricted_token_flag_works_by_itself() {
    let mut features = Features::with_defaults();
    features.enable(Feature::WindowsSandbox);

    assert_eq!(
        WindowsSandboxLevel::from_features(&features),
        WindowsSandboxLevel::RestrictedToken
    );
}

#[test]
fn no_flags_means_no_sandbox() {
    let features = Features::with_defaults();

    assert_eq!(
        WindowsSandboxLevel::from_features(&features),
        WindowsSandboxLevel::Disabled
    );
}

#[test]
fn elevated_wins_when_both_flags_are_enabled() {
    let mut features = Features::with_defaults();
    features.enable(Feature::WindowsSandbox);
    features.enable(Feature::WindowsSandboxElevated);

    assert_eq!(
        WindowsSandboxLevel::from_features(&features),
        WindowsSandboxLevel::Elevated
    );
}

#[test]
fn legacy_mode_prefers_elevated() {
    let mut entries = BTreeMap::new();
    entries.insert(
        "experimental_windows_sandbox".to_string(),
        /*value*/ true,
    );
    entries.insert("elevated_windows_sandbox".to_string(), /*value*/ true);

    assert_eq!(
        legacy_windows_sandbox_mode_from_entries(&entries),
        Some(WindowsSandboxModeToml::Elevated)
    );
}

#[test]
fn legacy_mode_supports_alias_key() {
    let mut entries = BTreeMap::new();
    entries.insert(
        "enable_experimental_windows_sandbox".to_string(),
        /*value*/ true,
    );

    assert_eq!(
        legacy_windows_sandbox_mode_from_entries(&entries),
        Some(WindowsSandboxModeToml::Unelevated)
    );
}

#[test]
fn resolve_windows_sandbox_mode_falls_back_to_legacy_keys() {
    let mut entries = BTreeMap::new();
    entries.insert(
        "experimental_windows_sandbox".to_string(),
        /*value*/ true,
    );
    let cfg = ConfigToml {
        features: Some(FeaturesToml::from(entries)),
        ..Default::default()
    };

    assert_eq!(
        resolve_windows_sandbox_mode(&cfg),
        Some(WindowsSandboxModeToml::Unelevated)
    );
}

#[test]
fn resolve_windows_sandbox_private_desktop_defaults_to_true() {
    assert!(resolve_windows_sandbox_private_desktop(
        &ConfigToml::default()
    ));
}

#[test]
fn resolve_windows_sandbox_private_desktop_respects_explicit_cfg_value() {
    let cfg = ConfigToml {
        windows: Some(WindowsToml {
            sandbox_private_desktop: Some(false),
            agent_shell: None,
            ..Default::default()
        }),
        ..Default::default()
    };

    assert!(!resolve_windows_sandbox_private_desktop(&cfg));
}

#[test]
fn resolve_windows_agent_shell_reads_explicit_cfg_value() {
    let cfg = ConfigToml {
        windows: Some(WindowsToml {
            agent_shell: Some(WindowsAgentShellToml::GitBash),
            ..Default::default()
        }),
        ..Default::default()
    };

    assert_eq!(
        resolve_windows_agent_shell(&cfg),
        Some(WindowsAgentShellToml::GitBash)
    );
}

#[test]
fn windows_agent_shell_deserializes_and_defaults_to_none() {
    let git_bash: ConfigToml = toml::from_str(
        r#"
[windows]
agent_shell = "git-bash"
"#,
    )
    .expect("Git Bash agent-shell config should deserialize");
    assert_eq!(
        resolve_windows_agent_shell(&git_bash),
        Some(WindowsAgentShellToml::GitBash)
    );

    let omitted: ConfigToml =
        toml::from_str("[windows]").expect("windows config without agent_shell should deserialize");
    assert_eq!(resolve_windows_agent_shell(&omitted), None);
}
