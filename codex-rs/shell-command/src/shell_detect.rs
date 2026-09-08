#[cfg(windows)]
use std::path::Path;
use std::path::PathBuf;

use serde::Deserialize;
use serde::Serialize;

#[derive(Debug, PartialEq, Eq, Clone, Copy, Serialize, Deserialize)]
pub enum ShellType {
    Zsh,
    Bash,
    PowerShell,
    Sh,
    Cmd,
}

impl ShellType {
    pub fn name(self) -> &'static str {
        match self {
            Self::Zsh => "zsh",
            Self::Bash => "bash",
            Self::PowerShell => "powershell",
            Self::Sh => "sh",
            Self::Cmd => "cmd",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DetectedShell {
    pub shell_type: ShellType,
    pub shell_path: PathBuf,
}

impl DetectedShell {
    pub fn name(&self) -> &'static str {
        self.shell_type.name()
    }
}

pub fn detect_shell_type(shell_path: impl AsRef<std::path::Path>) -> Option<ShellType> {
    let shell_path = shell_path.as_ref();
    match shell_path.as_os_str().to_str() {
        Some("zsh") => Some(ShellType::Zsh),
        Some("sh") => Some(ShellType::Sh),
        Some("cmd") => Some(ShellType::Cmd),
        Some("bash") => Some(ShellType::Bash),
        Some("pwsh") => Some(ShellType::PowerShell),
        Some("powershell") => Some(ShellType::PowerShell),
        _ => {
            let shell_name = shell_path.file_stem();
            if let Some(shell_name) = shell_name {
                let shell_name_path = std::path::Path::new(shell_name);
                if shell_name_path != shell_path {
                    return detect_shell_type(shell_name_path);
                }
            }
            None
        }
    }
}

#[cfg(unix)]
fn get_user_shell_path() -> Option<PathBuf> {
    let uid = unsafe { libc::getuid() };
    use std::ffi::CStr;
    use std::mem::MaybeUninit;
    use std::ptr;

    let mut passwd = MaybeUninit::<libc::passwd>::uninit();

    // We cannot use getpwuid here: it returns pointers into libc-managed
    // storage, which is not safe to read concurrently on all targets (the musl
    // static build used by the CLI can segfault when parallel callers race on
    // that buffer). getpwuid_r keeps the passwd data in caller-owned memory.
    let suggested_buffer_len = unsafe { libc::sysconf(libc::_SC_GETPW_R_SIZE_MAX) };
    let buffer_len = usize::try_from(suggested_buffer_len)
        .ok()
        .filter(|len| *len > 0)
        .unwrap_or(1024);
    let mut buffer = vec![0; buffer_len];

    loop {
        let mut result = ptr::null_mut();
        let status = unsafe {
            libc::getpwuid_r(
                uid,
                passwd.as_mut_ptr(),
                buffer.as_mut_ptr().cast(),
                buffer.len(),
                &mut result,
            )
        };

        if status == 0 {
            if result.is_null() {
                return None;
            }

            let passwd = unsafe { passwd.assume_init_ref() };
            if passwd.pw_shell.is_null() {
                return None;
            }

            let shell_path = unsafe { CStr::from_ptr(passwd.pw_shell) }
                .to_string_lossy()
                .into_owned();
            return Some(PathBuf::from(shell_path));
        }

        if status != libc::ERANGE {
            return None;
        }

        // Retry with a larger buffer until libc can materialize the passwd entry.
        let new_len = buffer.len().checked_mul(2)?;
        if new_len > 1024 * 1024 {
            return None;
        }
        buffer.resize(new_len, 0);
    }
}

#[cfg(not(unix))]
fn get_user_shell_path() -> Option<PathBuf> {
    None
}

fn file_exists(path: &std::path::Path) -> Option<PathBuf> {
    if std::fs::metadata(path).is_ok_and(|metadata| metadata.is_file()) {
        Some(PathBuf::from(path))
    } else {
        None
    }
}

// Store PowerShell can be inaccessible to the elevated sandbox account;
// WindowsApps also contains valid Codex frameworks.
fn is_inaccessible_windows_apps_powershell_path(path: &std::path::Path) -> bool {
    path.as_os_str()
        .to_string_lossy()
        .split(['\\', '/'])
        .skip_while(|component| !component.eq_ignore_ascii_case("WindowsApps"))
        .nth(1)
        .is_some_and(|component| {
            component.eq_ignore_ascii_case("pwsh.exe")
                || component.eq_ignore_ascii_case("powershell.exe")
                || component
                    .to_ascii_lowercase()
                    .starts_with("microsoft.powershell")
        })
}

fn targets_inaccessible_windows_apps_powershell(path: &std::path::Path) -> bool {
    is_inaccessible_windows_apps_powershell_path(path)
        || std::fs::canonicalize(path)
            .ok()
            .is_some_and(|resolved| is_inaccessible_windows_apps_powershell_path(&resolved))
}

fn is_elevated_sandbox_compatible_powershell_path(path: &std::path::Path) -> bool {
    if !path
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case("exe"))
    {
        return false;
    }

    !targets_inaccessible_windows_apps_powershell(path)
}

fn get_elevated_sandbox_compatible_powershell_path(
    binary_name: &str,
    fallback_paths: &[&str],
) -> Option<PathBuf> {
    if let Ok(mut paths) = which::which_all(binary_name)
        && let Some(path) = paths.find(|path| is_elevated_sandbox_compatible_powershell_path(path))
    {
        return Some(path);
    }

    for path in fallback_paths {
        let path = std::path::Path::new(path);
        if is_elevated_sandbox_compatible_powershell_path(path)
            && let Some(path) = file_exists(path)
        {
            return Some(path);
        }
    }

    None
}

fn get_shell_path(
    shell_type: ShellType,
    binary_name: &str,
    fallback_paths: &[&str],
) -> Option<PathBuf> {
    let default_shell_path = get_user_shell_path();
    if let Some(default_shell_path) = default_shell_path
        && detect_shell_type(&default_shell_path) == Some(shell_type)
        && file_exists(&default_shell_path).is_some()
    {
        return Some(default_shell_path);
    }

    if let Ok(path) = which::which(binary_name) {
        return Some(path);
    }

    for path in fallback_paths {
        if let Some(path) = file_exists(std::path::Path::new(path)) {
            return Some(path);
        }
    }

    None
}

const ZSH_FALLBACK_PATHS: &[&str] = &["/bin/zsh"];

fn get_zsh_shell() -> Option<DetectedShell> {
    let shell_path = get_shell_path(ShellType::Zsh, "zsh", ZSH_FALLBACK_PATHS);

    shell_path.map(|shell_path| DetectedShell {
        shell_type: ShellType::Zsh,
        shell_path,
    })
}

const BASH_FALLBACK_PATHS: &[&str] = &["/bin/bash", "/usr/bin/bash"];

fn get_bash_shell() -> Option<DetectedShell> {
    let shell_path = get_shell_path(ShellType::Bash, "bash", BASH_FALLBACK_PATHS);

    shell_path.map(|shell_path| DetectedShell {
        shell_type: ShellType::Bash,
        shell_path,
    })
}

const SH_FALLBACK_PATHS: &[&str] = &["/bin/sh"];

#[cfg(windows)]
fn git_bash_candidate_paths_for_root(git_root: &Path) -> Vec<PathBuf> {
    vec![
        git_root.join("bin").join("bash.exe"),
        git_root.join("usr").join("bin").join("bash.exe"),
    ]
}

#[cfg(windows)]
fn is_git_for_windows_root(git_root: &Path) -> bool {
    [
        git_root.join("cmd").join("git.exe"),
        git_root.join("bin").join("git.exe"),
        git_root.join("mingw64").join("bin").join("git.exe"),
        git_root.join("usr").join("bin").join("git.exe"),
    ]
    .into_iter()
    .any(|path| file_exists(&path).is_some())
}

#[cfg(windows)]
fn root_owns_git_bash(git_root: &Path) -> bool {
    git_bash_candidate_paths_for_root(git_root)
        .iter()
        .any(|candidate| file_exists(candidate).is_some())
}

#[cfg(windows)]
fn git_root_for_executable(git_executable: &Path) -> Option<PathBuf> {
    git_executable
        .ancestors()
        .skip(1)
        // Git for Windows puts git.exe at most three levels below its install
        // root: `cmd`, `bin`, or `mingw64\bin`. `<root>\mingw64` holds the real
        // `bin\git.exe`, so it satisfies the root predicate on its own and would
        // shadow `<root>` while owning no bash.exe at all. Requiring a Git Bash
        // keeps the walk going until it reaches the actual install root, which
        // matters because `mingw64\bin` is the PATH entry Git Bash exports and
        // the one this fork's launcher prepends.
        .take(3)
        .find(|candidate| is_git_for_windows_root(candidate) && root_owns_git_bash(candidate))
        .map(Path::to_path_buf)
}

#[cfg(windows)]
fn git_roots_on_path() -> Vec<PathBuf> {
    let Some(path) = std::env::var_os("PATH") else {
        return Vec::new();
    };

    std::env::split_paths(&path)
        .map(|directory| directory.join("git.exe"))
        .filter_map(|git_executable| {
            file_exists(&git_executable)
                .as_deref()
                .and_then(git_root_for_executable)
        })
        .collect()
}

#[cfg(windows)]
fn git_root_for_bash_executable(bash_executable: &Path) -> Option<PathBuf> {
    let bin_dir = bash_executable.parent()?;
    if !bin_dir
        .file_name()?
        .to_string_lossy()
        .eq_ignore_ascii_case("bin")
    {
        return None;
    }

    let parent = bin_dir.parent()?;
    if parent
        .file_name()
        .is_some_and(|name| name.to_string_lossy().eq_ignore_ascii_case("usr"))
    {
        parent.parent().map(Path::to_path_buf)
    } else {
        Some(parent.to_path_buf())
    }
}

#[cfg(windows)]
fn push_unique_path(paths: &mut Vec<PathBuf>, candidate: PathBuf) {
    // Windows paths are case-insensitive; PATH and the environment variables
    // frequently spell the same install root differently.
    if !paths.iter().any(|existing| {
        existing
            .as_os_str()
            .eq_ignore_ascii_case(candidate.as_os_str())
    }) {
        paths.push(candidate);
    }
}

#[cfg(windows)]
fn git_bash_candidate_paths() -> Vec<PathBuf> {
    // Prefer the Git installation the user actually runs (first on PATH), then
    // the standard per-user and machine-wide install locations.
    let mut roots = git_roots_on_path();
    if let Some(local_app_data) = std::env::var_os("LocalAppData") {
        roots.push(PathBuf::from(local_app_data).join("Programs").join("Git"));
    }
    for variable in ["ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"] {
        if let Some(program_files) = std::env::var_os(variable) {
            roots.push(PathBuf::from(program_files).join("Git"));
        }
    }

    // Keep deterministic fallback paths for environments that do not expose the
    // standard Windows environment variables (for example stripped-down shells).
    roots.extend([
        PathBuf::from(r"C:\Program Files\Git"),
        PathBuf::from(r"C:\Program Files (x86)\Git"),
    ]);

    let mut candidates = Vec::new();
    for root in roots {
        for candidate in git_bash_candidate_paths_for_root(&root) {
            push_unique_path(&mut candidates, candidate);
        }
    }
    candidates
}

/// Resolves Git for Windows' Bash executable without consulting a generic
/// `bash` lookup, which could otherwise select WSL or an app-execution alias.
///
/// Always returns `None` on non-Windows platforms.
pub fn git_bash_shell() -> Option<DetectedShell> {
    #[cfg(windows)]
    {
        git_bash_candidate_paths()
            .into_iter()
            .find_map(|path| {
                let git_root = git_root_for_bash_executable(&path)?;
                is_git_for_windows_root(&git_root)
                    .then(|| file_exists(&path))
                    .flatten()
            })
            .map(|shell_path| DetectedShell {
                shell_type: ShellType::Bash,
                shell_path,
            })
    }

    #[cfg(not(windows))]
    {
        None
    }
}

fn get_sh_shell() -> Option<DetectedShell> {
    let shell_path = get_shell_path(ShellType::Sh, "sh", SH_FALLBACK_PATHS);

    shell_path.map(|shell_path| DetectedShell {
        shell_type: ShellType::Sh,
        shell_path,
    })
}

// Note the `pwsh` and `powershell` fallback paths are where the respective
// shells are commonly installed on GitHub Actions Windows runners, but may not
// be present on all Windows machines:
// https://docs.github.com/en/actions/tutorials/build-and-test-code/powershell

#[cfg(windows)]
const PWSH_FALLBACK_PATHS: &[&str] = &[r#"C:\Program Files\PowerShell\7\pwsh.exe"#];
#[cfg(not(windows))]
const PWSH_FALLBACK_PATHS: &[&str] = &["/usr/local/bin/pwsh"];

#[cfg(windows)]
const POWERSHELL_FALLBACK_PATHS: &[&str] =
    &[r#"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"#];
#[cfg(not(windows))]
const POWERSHELL_FALLBACK_PATHS: &[&str] = &[];

fn get_powershell_shell() -> Option<DetectedShell> {
    let shell_path =
        get_shell_path(ShellType::PowerShell, "pwsh", PWSH_FALLBACK_PATHS).or_else(|| {
            get_shell_path(
                ShellType::PowerShell,
                "powershell",
                POWERSHELL_FALLBACK_PATHS,
            )
        });

    shell_path.map(|shell_path| DetectedShell {
        shell_type: ShellType::PowerShell,
        shell_path,
    })
}

/// Returns a replacement only when shell_path targets Store PowerShell and
/// an elevated sandbox-compatible PowerShell executable can be discovered.
///
/// The caller owns the elevated-sandbox policy decision. Normal shell discovery
/// intentionally keeps the user's ordered PATH selection unchanged.
pub fn fallback_powershell_shell_for_elevated_windows_sandbox(
    shell_path: &std::path::Path,
) -> Option<DetectedShell> {
    if !cfg!(windows) || !targets_inaccessible_windows_apps_powershell(shell_path) {
        return None;
    }

    let shell_path = get_elevated_sandbox_compatible_powershell_path("pwsh", PWSH_FALLBACK_PATHS)
        .or_else(|| {
        get_elevated_sandbox_compatible_powershell_path("powershell", POWERSHELL_FALLBACK_PATHS)
    })?;

    Some(DetectedShell {
        shell_type: ShellType::PowerShell,
        shell_path,
    })
}

fn get_cmd_shell() -> Option<DetectedShell> {
    let shell_path = get_shell_path(ShellType::Cmd, "cmd", &[]);

    shell_path.map(|shell_path| DetectedShell {
        shell_type: ShellType::Cmd,
        shell_path,
    })
}

pub fn ultimate_fallback_shell() -> DetectedShell {
    if cfg!(windows) {
        DetectedShell {
            shell_type: ShellType::Cmd,
            shell_path: PathBuf::from("cmd.exe"),
        }
    } else {
        DetectedShell {
            shell_type: ShellType::Sh,
            shell_path: PathBuf::from("/bin/sh"),
        }
    }
}

/// Uses the model-provided path only to select a shell type, then discovers its executable.
pub fn get_shell_by_model_provided_path(shell_path: &PathBuf) -> DetectedShell {
    detect_shell_type(shell_path)
        .and_then(get_shell)
        .unwrap_or_else(ultimate_fallback_shell)
}

pub fn get_shell(shell_type: ShellType) -> Option<DetectedShell> {
    match shell_type {
        ShellType::Zsh => get_zsh_shell(),
        ShellType::Bash => get_bash_shell(),
        ShellType::PowerShell => get_powershell_shell(),
        ShellType::Sh => get_sh_shell(),
        ShellType::Cmd => get_cmd_shell(),
    }
}

pub fn default_user_shell() -> DetectedShell {
    default_user_shell_from_path(get_user_shell_path())
}

pub fn default_user_shell_from_path(user_shell_path: Option<PathBuf>) -> DetectedShell {
    if cfg!(windows) {
        get_shell(ShellType::PowerShell).unwrap_or_else(ultimate_fallback_shell)
    } else {
        let user_default_shell = user_shell_path
            .and_then(|shell| detect_shell_type(&shell))
            .and_then(get_shell);

        let shell_with_fallback = if cfg!(target_os = "macos") {
            user_default_shell
                .or_else(|| get_shell(ShellType::Zsh))
                .or_else(|| get_shell(ShellType::Bash))
        } else {
            user_default_shell
                .or_else(|| get_shell(ShellType::Bash))
                .or_else(|| get_shell(ShellType::Zsh))
        };

        shell_with_fallback.unwrap_or_else(ultimate_fallback_shell)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pretty_assertions::assert_eq;

    #[cfg(windows)]
    #[test]
    fn git_bash_candidates_include_standard_git_for_windows_paths() {
        let candidates = git_bash_candidate_paths();
        assert!(candidates.contains(&PathBuf::from(r"C:\Program Files\Git\bin\bash.exe")));
        assert!(candidates.contains(&PathBuf::from(r"C:\Program Files\Git\usr\bin\bash.exe")));
    }

    #[cfg(windows)]
    fn write_stub_tree(root: &Path, relative_paths: &[&str]) {
        for relative in relative_paths {
            let path = root.join(relative);
            std::fs::create_dir_all(path.parent().expect("stub parent")).expect("create stub dirs");
            std::fs::write(&path, b"").expect("write stub");
        }
    }

    #[cfg(windows)]
    #[test]
    fn git_root_for_executable_walks_past_the_mingw64_subtree() {
        // `<root>\mingw64\bin\git.exe` is the real git binary, so `<root>\mingw64`
        // looks like an install root while owning no bash.exe. The walk has to
        // reach `<root>`, or a Git install outside the well-known directories is
        // never found even though it is first on PATH.
        let temp = tempfile::tempdir().expect("temp dir");
        let root = temp.path().join("PortableGit");
        write_stub_tree(
            &root,
            &[r"mingw64\bin\git.exe", r"bin\bash.exe", r"usr\bin\bash.exe"],
        );

        assert_eq!(
            git_root_for_executable(&root.join(r"mingw64\bin\git.exe")),
            Some(root)
        );
    }

    #[cfg(windows)]
    #[test]
    fn git_root_for_executable_accepts_the_cmd_shim() {
        let temp = tempfile::tempdir().expect("temp dir");
        let root = temp.path().join("Git");
        write_stub_tree(&root, &[r"cmd\git.exe", r"bin\bash.exe"]);

        assert_eq!(
            git_root_for_executable(&root.join(r"cmd\git.exe")),
            Some(root)
        );
    }

    #[cfg(windows)]
    #[test]
    fn git_root_for_executable_rejects_a_root_without_git_bash() {
        // A lone git.exe (scoop shim, a stripped install) must not be reported
        // as a Git Bash root; discovery falls through to the next candidate.
        let temp = tempfile::tempdir().expect("temp dir");
        let root = temp.path().join("GitWithoutBash");
        write_stub_tree(&root, &[r"cmd\git.exe"]);

        assert_eq!(git_root_for_executable(&root.join(r"cmd\git.exe")), None);
    }

    #[cfg(windows)]
    #[test]
    fn git_bash_candidates_are_unique_ignoring_case() {
        let candidates = git_bash_candidate_paths();
        for (index, candidate) in candidates.iter().enumerate() {
            assert!(
                !candidates[index + 1..].iter().any(|other| other
                    .as_os_str()
                    .eq_ignore_ascii_case(candidate.as_os_str())),
                "duplicate Git Bash candidate: {}",
                candidate.display()
            );
        }
    }

    #[cfg(windows)]
    #[test]
    fn git_bash_candidates_support_a_custom_git_install_root() {
        let root = PathBuf::from(r"D:\tools\PortableGit");
        assert_eq!(
            git_bash_candidate_paths_for_root(&root),
            vec![
                root.join("bin").join("bash.exe"),
                root.join("usr").join("bin").join("bash.exe"),
            ]
        );
    }

    #[cfg(windows)]
    #[test]
    fn git_bash_root_is_derived_from_the_bash_layout() {
        assert_eq!(
            git_root_for_bash_executable(Path::new(r"D:\tools\PortableGit\usr\bin\bash.exe")),
            Some(PathBuf::from(r"D:\tools\PortableGit"))
        );
        assert_eq!(
            git_root_for_bash_executable(Path::new(r"D:\tools\PortableGit\bin\bash.exe")),
            Some(PathBuf::from(r"D:\tools\PortableGit"))
        );
        assert_eq!(
            git_root_for_bash_executable(Path::new(r"C:\Windows\System32\bash.exe")),
            None
        );
    }

    #[cfg(not(windows))]
    #[test]
    fn git_bash_shell_is_unavailable_off_windows() {
        assert_eq!(git_bash_shell(), None);
    }

    #[test]
    fn elevated_sandbox_filter_rejects_store_and_script_powershell_paths() {
        for path in [
            r"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe",
            r"C:\Program Files\WindowsApps\Microsoft.PowerShellPreview_8wekyb3d8bbwe\pwsh.exe",
            r"C:\Users\user\AppData\Local\Microsoft\WindowsApps\pwsh.exe",
            r"C:\Users\user\AppData\Local\Microsoft\WindowsApps\powershell.exe",
            r"C:\Users\user\AppData\Local\Microsoft\WindowsApps\Microsoft.PowerShell_8wekyb3d8bbwe\pwsh.exe",
            r"C:\PROGRAM FILES\WINDOWSAPPS\MICROSOFT.POWERSHELL\PWSH.EXE",
            r"C:\portable\pwsh.cmd",
        ] {
            assert!(!is_elevated_sandbox_compatible_powershell_path(
                std::path::Path::new(path)
            ));
        }

        for path in [
            r"C:\Program Files\PowerShell\7\pwsh.exe",
            r"C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-813-10124-0_26.813.10124.0_x64__3k8sg7r9htsxt\dependencies\native\powershell\pwsh.exe",
            r"C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-813-10124-0_26.813.10124.0_arm64__3k8sg7r9htsxt\dependencies\native\powershell\pwsh.exe",
            r"C:\PROGRAM FILES\WINDOWSAPPS\OPENAI.CODEXPRIMARYRUNTIME.V26-813-10124-0\DEPENDENCIES\NATIVE\POWERSHELL\PWSH.EXE",
            r"\\?\C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-813-10124-0\dependencies\native\powershell\pwsh.exe",
            r"C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe",
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            r"C:\portable\NotWindowsApps\pwsh.EXE",
        ] {
            assert!(is_elevated_sandbox_compatible_powershell_path(
                std::path::Path::new(path)
            ));
        }
    }

    #[test]
    fn elevated_sandbox_filter_preserves_ordered_fallback() {
        let portable = PathBuf::from(
            r"C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe",
        );
        let found = [
            PathBuf::from(
                r"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe",
            ),
            PathBuf::from(r"C:\Users\user\AppData\Local\Microsoft\WindowsApps\pwsh.exe"),
            PathBuf::from(r"C:\runtime\dependencies\bin\fallback\pwsh.cmd"),
            portable.clone(),
            PathBuf::from(r"C:\Program Files\PowerShell\7\pwsh.exe"),
        ]
        .into_iter()
        .find(|path| is_elevated_sandbox_compatible_powershell_path(path));

        assert_eq!(found, Some(portable));
    }

    #[test]
    fn test_detect_shell_type() {
        assert_eq!(
            detect_shell_type(PathBuf::from("zsh")),
            Some(ShellType::Zsh)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("bash")),
            Some(ShellType::Bash)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("pwsh")),
            Some(ShellType::PowerShell)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("powershell")),
            Some(ShellType::PowerShell)
        );
        assert_eq!(detect_shell_type(PathBuf::from("fish")), None);
        assert_eq!(detect_shell_type(PathBuf::from("other")), None);
        assert_eq!(
            detect_shell_type(PathBuf::from("/bin/zsh")),
            Some(ShellType::Zsh)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("/bin/bash")),
            Some(ShellType::Bash)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("/usr/bin/bash")),
            Some(ShellType::Bash)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("powershell.exe")),
            Some(ShellType::PowerShell)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from(if cfg!(windows) {
                "C:\\windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
            } else {
                "/usr/local/bin/pwsh"
            })),
            Some(ShellType::PowerShell)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("pwsh.exe")),
            Some(ShellType::PowerShell)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("/usr/local/bin/pwsh")),
            Some(ShellType::PowerShell)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("/bin/sh")),
            Some(ShellType::Sh)
        );
        assert_eq!(detect_shell_type(PathBuf::from("sh")), Some(ShellType::Sh));
        assert_eq!(
            detect_shell_type(PathBuf::from("cmd")),
            Some(ShellType::Cmd)
        );
        assert_eq!(
            detect_shell_type(PathBuf::from("cmd.exe")),
            Some(ShellType::Cmd)
        );
    }
}
