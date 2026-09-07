//! End-to-end check that `git_bash_shell` finds a real Git for Windows install.
//!
//! The unit tests in `shell_detect` only exercise path construction; this test
//! runs discovery against whatever is installed on the machine. Because not
//! every developer machine has Git for Windows, the "must be found" assertion
//! is opt-in: CI sets `CODEX_REQUIRE_GIT_BASH=1`, elsewhere the test reports
//! what it found and passes.

use codex_shell_command::shell_detect::ShellType;
use codex_shell_command::shell_detect::git_bash_shell;

#[test]
fn git_bash_discovery_resolves_a_usable_git_for_windows_bash() {
    let required = std::env::var_os("CODEX_REQUIRE_GIT_BASH").is_some_and(|value| value == "1");
    let Some(shell) = git_bash_shell() else {
        assert!(
            !required,
            "CODEX_REQUIRE_GIT_BASH=1 but no Git for Windows Bash was discovered"
        );
        println!("no Git for Windows install discovered; strict assertions skipped");
        return;
    };

    assert_eq!(shell.shell_type, ShellType::Bash);
    assert!(
        shell.shell_path.is_file(),
        "discovered shell {} does not exist",
        shell.shell_path.display()
    );

    let path = shell.shell_path.to_string_lossy().to_lowercase();
    assert!(
        path.ends_with("bash.exe"),
        "discovered shell {path} is not bash.exe"
    );
    // WSL ships a `bash.exe` launcher in System32; selecting it would run the
    // agent's commands in a Linux VM instead of Git Bash.
    assert!(
        !path.contains("\\windows\\system32\\") && !path.contains("/windows/system32/"),
        "discovered shell {path} is the WSL launcher"
    );
    println!("resolved Git Bash: {}", shell.shell_path.display());
}
