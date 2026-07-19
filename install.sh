#!/usr/bin/env bash

set -Eeuo pipefail

SUPABASE_VERSION="2.109.1"
SUPA_CC_VERSION="0.5.6"
HOMEBREW_INSTALL_REVISION="4b0227cf8416504142d23893368c2e1d211d5191"
HOMEBREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/${HOMEBREW_INSTALL_REVISION}/install.sh"
SUPABASE_RELEASE_URL="https://github.com/supabase/cli/releases/download/v${SUPABASE_VERSION}"
SUPA_CC_REPOSITORY="https://github.com/dgabreuu/supa.cc.git"

YES=0
DRY_RUN=0
OS=""
DISTRO="none"
DISTRO_ID=""
DISTRO_ID_LIKE=""
DISTRO_VERSION=""
DISTRO_SOURCE=""
ARCH=""
TEMP_DIR=""
PLAN=()

usage() {
    cat <<'EOF'
Install Supa.cc and its required runtime dependencies.

Usage: install.sh [--yes] [--dry-run] [--help]

  --yes      Skip the Supa.cc confirmation. Native administrator prompts remain.
  --dry-run  Print the installation plan without changing the system.
  --help     Show this help.
EOF
}

fail() {
    printf 'Supa.cc installer failed during %s: %s\n' "${PHASE:-planning}" "$1" >&2
    exit "${2:-1}"
}

warn() {
    printf 'Warning: %s\n' "$1" >&2
}

has_command() {
    command -v "$1" >/dev/null 2>&1
}

add_plan() {
    PLAN[${#PLAN[@]}]="$*"
}

print_plan() {
    printf 'Supa.cc installation plan (%s/%s):\n' "${OS:-unknown}" "${ARCH:-unknown}"
    local item
    for item in "${PLAN[@]}"; do
        printf '  - %s\n' "$item"
    done
}

parse_arguments() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --yes) YES=1 ;;
            --dry-run) DRY_RUN=1 ;;
            --help) usage; exit 0 ;;
            *) fail "Unknown option: $1" 2 ;;
        esac
        shift
    done
}

read_os_release_value() {
    local key="$1" file="$2"
    [ -r "$file" ] || return 0
    awk -v key="$key" '
        {
            separator = index($0, "=")
            if (!separator) next
            name = substr($0, 1, separator - 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
            if (name != key) next
            value = substr($0, separator + 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            if (length(value) >= 2) {
                first = substr(value, 1, 1)
                last = substr(value, length(value), 1)
                if ((first == "\"" || first == "\047") && last == first) {
                    value = substr(value, 2, length(value) - 2)
                }
            }
            result = value
            found = 1
        }
        END { if (found) print result }
    ' "$file" 2>/dev/null || true
}

read_linux_metadata() {
    local file="${1:-/etc/os-release}"
    DISTRO_ID="$(read_os_release_value ID "$file")"
    DISTRO_ID_LIKE="$(read_os_release_value ID_LIKE "$file")"
    DISTRO_VERSION="$(read_os_release_value VERSION_ID "$file")"
}

normalize_linux_identifier() {
    printf '%s\n' "$1" | awk '{ sub(/^[[:space:]]+/, ""); sub(/[[:space:]]+$/, ""); print tolower($0) }'
}

is_supported_linux_distribution() {
    case "$1" in
        debian|ubuntu|arch|fedora) return 0 ;;
        *) return 1 ;;
    esac
}

resolve_linux_distribution() {
    local candidate
    DISTRO=""
    DISTRO_SOURCE=""

    candidate="$(normalize_linux_identifier "$1")"
    if is_supported_linux_distribution "$candidate"; then
        DISTRO="$candidate"
        DISTRO_SOURCE="id"
        return 0
    fi

    while IFS= read -r candidate; do
        candidate="$(normalize_linux_identifier "$candidate")"
        if is_supported_linux_distribution "$candidate"; then
            DISTRO="$candidate"
            DISTRO_SOURCE="id_like"
            return 0
        fi
    done < <(printf '%s\n' "$2" | awk '{ for (i = 1; i <= NF; i++) print $i }')

    return 1
}

detect_environment() {
    case "$(uname -s)" in
        Darwin) OS="macos" ;;
        Linux) OS="linux" ;;
        *) fail "Only macOS and supported Linux distributions are supported by this installer." ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64) ARCH="amd64" ;;
        arm64|aarch64) ARCH="arm64" ;;
        *) fail "Only x64 and arm64 systems are supported." ;;
    esac

    if [ "$OS" = "linux" ]; then
        local reported_distribution
        read_linux_metadata
        if ! resolve_linux_distribution "$DISTRO_ID" "$DISTRO_ID_LIKE"; then
            reported_distribution="$(normalize_linux_identifier "$DISTRO_ID")"
            fail "Linux distribution '${reported_distribution:-unknown}' is not supported. Use Debian, Ubuntu, Arch, or Fedora."
        fi
        validate_linux_version
    fi
}

validate_linux_version() {
    [ "$DISTRO_SOURCE" = "id_like" ] && return 0
    local major="${DISTRO_VERSION%%.*}"
    case "$DISTRO" in
        debian)
            case "$major" in *[!0-9]*|'') fail "Debian version could not be verified for the Python 3.11 requirement." ;; esac
            [ "$major" -ge 12 ] || fail "Debian 12 or newer is required to provide Python 3.11 or newer."
            ;;
        ubuntu)
            case "$major" in *[!0-9]*|'') fail "Ubuntu version could not be verified for the Python 3.11 requirement." ;; esac
            [ "$major" -ge 24 ] || fail "Ubuntu 24.04 or newer is required to provide Python 3.11 or newer."
            ;;
        arch|fedora) ;;
        *) fail "This Linux distribution is not supported." ;;
    esac
}

version_at_least() {
    local actual="$1" minimum="$2"
    local actual_major actual_minor actual_patch minimum_major minimum_minor minimum_patch
    IFS=. read -r actual_major actual_minor actual_patch <<EOF
$actual
EOF
    IFS=. read -r minimum_major minimum_minor minimum_patch <<EOF
$minimum
EOF
    case "$actual_major$actual_minor$actual_patch$minimum_major$minimum_minor$minimum_patch" in
        *[!0-9]*) return 1 ;;
    esac
    [ "$actual_major" -gt "$minimum_major" ] ||
        { [ "$actual_major" -eq "$minimum_major" ] && [ "$actual_minor" -gt "$minimum_minor" ]; } ||
        { [ "$actual_major" -eq "$minimum_major" ] && [ "$actual_minor" -eq "$minimum_minor" ] && [ "$actual_patch" -ge "$minimum_patch" ]; }
}

supabase_compatible() {
    has_command supabase || return 1
    local output version
    output="$(supabase --version 2>/dev/null || true)"
    version="$(printf '%s\n' "$output" | awk '{for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+$/) {print $i; exit}}')"
    [ -n "$version" ] && version_at_least "$version" "$SUPABASE_VERSION"
}

supa_compatible() {
    has_command supa.cc || return 1
    local output version
    output="$(supa.cc --version 2>/dev/null || true)"
    version="$(printf '%s\n' "$output" | awk '{for (i=1; i<=NF; i++) if ($i ~ /^[0-9]+\.[0-9]+\.[0-9]+$/) {print $i; exit}}')"
    [ -n "$version" ] && version_at_least "$version" "$SUPA_CC_VERSION"
}

python_compatible() {
    local python="$1"
    has_command "$python" || return 1
    "$python" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1
}

select_python() {
    if python_compatible python3; then
        printf '%s\n' python3
    elif python_compatible python; then
        printf '%s\n' python
    else
        return 1
    fi
}

resolve_command_path() {
    local command_path
    command_path="$(command -v "$1" 2>/dev/null || true)"
    if [ -n "$command_path" ] && has_command realpath; then
        realpath "$command_path" 2>/dev/null || printf '%s\n' "$command_path"
    else
        printf '%s\n' "$command_path"
    fi
}

detect_supa_channel() {
    has_command supa.cc || { printf '%s\n' missing; return; }
    local path
    path="$(resolve_command_path supa.cc)"
    case "$path" in
        */Cellar/supa-cc/*) printf '%s\n' homebrew ;;
        */pipx/venvs/supa-cc/*|*/pipx/venvs/supa.cc/*) printf '%s\n' pipx ;;
        *) printf '%s\n' other ;;
    esac
}

check_installation_channel() {
    local actual expected
    actual="$(detect_supa_channel)"
    expected="pipx"
    [ "$OS" = "macos" ] && expected="homebrew"
    if [ "$actual" != "missing" ] && [ "$actual" != "$expected" ]; then
        fail "Supa.cc is already installed through '${actual}'. Remove that installation before using the ${expected} bootstrap."
    fi
}

linux_package_command() {
    case "$DISTRO" in
        debian|ubuntu) printf '%s\n' "apt install python3 python3-venv pipx gnome-keyring curl ca-certificates tar" ;;
        arch) printf '%s\n' "pacman -S python python-pipx gnome-keyring curl ca-certificates tar" ;;
        fedora) printf '%s\n' "dnf install python3 pipx gnome-keyring curl ca-certificates tar" ;;
        *) return 1 ;;
    esac
}

linux_prerequisites_ready() {
    select_python >/dev/null 2>&1 || return 1
    has_command pipx || return 1
    has_command gnome-keyring-daemon || return 1
    has_command curl || return 1
    has_command tar || return 1
    if [ "$DISTRO" = "debian" ] || [ "$DISTRO" = "ubuntu" ]; then
        python3 -c 'import venv' >/dev/null 2>&1 || return 1
    fi
}

build_plan() {
    PLAN=()
    if [ "$OS" = "macos" ]; then
        local supa_formula_needed=0
        if ! has_command supa.cc || ! supa_compatible; then
            supa_formula_needed=1
        fi
        if ! locate_brew >/dev/null 2>&1; then
            add_plan "Download and run pinned Homebrew installer: $HOMEBREW_INSTALL_URL"
        fi
        add_plan "Load brew shellenv in this session"
        if ! supabase_compatible || [ "$supa_formula_needed" -eq 1 ]; then
            add_plan "brew install supabase/tap/supabase"
        fi
        if ! has_command supa.cc; then
            add_plan "brew tap dgabreuu/supa-cc $SUPA_CC_REPOSITORY"
            add_plan "brew install dgabreuu/supa-cc/supa-cc"
        elif ! supa_compatible; then
            add_plan "brew upgrade dgabreuu/supa-cc/supa-cc"
        fi
    else
        if ! linux_prerequisites_ready; then
            add_plan "sudo $(linux_package_command)"
        fi
        if ! supabase_compatible; then
            local artifact="supabase_${SUPABASE_VERSION}_linux_${ARCH}.tar.gz"
            add_plan "Download $SUPABASE_RELEASE_URL/$artifact"
            add_plan "Download $SUPABASE_RELEASE_URL/checksums.txt and require a valid SHA-256 checksum"
            add_plan "Install Supabase CLI in the user executable directory"
        fi
        if ! has_command supa.cc; then
            add_plan "pipx ensurepath"
            add_plan "pipx install supa.cc"
            add_plan "Update PATH for the current session"
        elif ! supa_compatible; then
            add_plan "pipx upgrade supa.cc"
        fi
    fi
    add_plan "Run supa.cc --version"
    add_plan "Run supa.cc doctor --installation-check"
}

tty_available() {
    ( : </dev/tty ) 2>/dev/null
}

confirm_plan() {
    [ "$YES" -eq 1 ] && return 0
    if ! tty_available; then
        fail "No interactive /dev/tty is available. Re-run with --yes after reviewing the plan." 2
    fi
    local answer
    printf 'Continue? [y/N] ' >/dev/tty
    IFS= read -r answer </dev/tty || answer=""
    case "$answer" in
        y|Y|yes|YES) ;;
        *) fail "Installation cancelled." 2 ;;
    esac
}

cleanup() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi
}

make_temp_dir() {
    TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/supa-cc-install.XXXXXX")"
}

download() {
    local url="$1" destination="$2"
    curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$url" --output "$destination"
}

sha256_file() {
    if has_command sha256sum; then
        sha256sum "$1" | awk '{print $1}'
    elif has_command shasum; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        return 1
    fi
}

verify_checksum() {
    local artifact="$1" checksums="$2" filename expected actual
    filename="$(basename "$artifact")"
    expected="$(awk -v filename="$filename" '$2 == filename {print $1; exit}' "$checksums")"
    case "$expected" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
        *) printf 'Missing or invalid checksum for %s.\n' "$filename" >&2; return 1 ;;
    esac
    actual="$(sha256_file "$artifact")" || { printf 'No SHA-256 tool is available.\n' >&2; return 1; }
    if [ "$actual" != "$expected" ]; then
        printf 'SHA-256 checksum mismatch for %s.\n' "$filename" >&2
        return 1
    fi
}

root_command() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif has_command sudo; then
        sudo "$@"
    else
        fail "Administrator privileges are required to install system packages. Install sudo or run the package command as root."
    fi
}

locate_brew() {
    if has_command brew; then
        command -v brew
    elif [ -x /opt/homebrew/bin/brew ]; then
        printf '%s\n' /opt/homebrew/bin/brew
    elif [ -x /usr/local/bin/brew ]; then
        printf '%s\n' /usr/local/bin/brew
    else
        return 1
    fi
}

execute_macos() {
    PHASE="Homebrew setup"
    if ! locate_brew >/dev/null 2>&1; then
        download "$HOMEBREW_INSTALL_URL" "$TEMP_DIR/homebrew-install.sh"
        NONINTERACTIVE=1 /bin/bash "$TEMP_DIR/homebrew-install.sh"
    fi
    local brew_binary
    brew_binary="$(locate_brew)" || fail "Homebrew installation completed but brew was not found."
    eval "$("$brew_binary" shellenv)"

    if ! supabase_compatible || ! has_command supa.cc || ! supa_compatible; then
        PHASE="Supabase CLI installation"
        "$brew_binary" install supabase/tap/supabase
    fi
    if ! has_command supa.cc; then
        PHASE="Supa.cc installation"
        "$brew_binary" tap dgabreuu/supa-cc "$SUPA_CC_REPOSITORY"
        "$brew_binary" install dgabreuu/supa-cc/supa-cc
    elif ! supa_compatible; then
        PHASE="Supa.cc upgrade"
        "$brew_binary" upgrade dgabreuu/supa-cc/supa-cc
    fi
}

execute_linux() {
    PHASE="Linux prerequisites"
    if ! linux_prerequisites_ready; then
        case "$DISTRO" in
            debian|ubuntu)
                root_command apt update
                root_command apt install -y python3 python3-venv pipx gnome-keyring curl ca-certificates tar
                ;;
            arch) root_command pacman -S --needed --noconfirm python python-pipx gnome-keyring curl ca-certificates tar ;;
            fedora) root_command dnf install -y python3 pipx gnome-keyring curl ca-certificates tar ;;
        esac
    fi

    local python artifact checksums user_bin
    python="$(select_python)" || fail "Python 3.11 or newer is unavailable after package installation."
    user_bin="$HOME/.local/bin"
    mkdir -p "$user_bin"

    if ! supabase_compatible; then
        PHASE="Supabase CLI download"
        artifact="supabase_${SUPABASE_VERSION}_linux_${ARCH}.tar.gz"
        checksums="$TEMP_DIR/checksums.txt"
        download "$SUPABASE_RELEASE_URL/$artifact" "$TEMP_DIR/$artifact"
        download "$SUPABASE_RELEASE_URL/checksums.txt" "$checksums"
        verify_checksum "$TEMP_DIR/$artifact" "$checksums" || fail "Supabase CLI checksum verification failed."
        tar -xzf "$TEMP_DIR/$artifact" -C "$TEMP_DIR" supabase
        install -m 0755 "$TEMP_DIR/supabase" "$user_bin/supabase"
    fi

    export PATH="$user_bin:$PATH"
    has_command pipx || fail "pipx is unavailable after package installation."
    if ! has_command supa.cc; then
        PHASE="pipx configuration"
        pipx ensurepath
        pipx install supa.cc
    elif ! supa_compatible; then
        PHASE="Supa.cc upgrade"
        pipx upgrade supa.cc
    fi
}

prompt_installation_retry() {
    printf 'Resolve the diagnostic shown above, then press Enter to retry. ' >/dev/tty
    IFS= read -r _ </dev/tty || true
}

verify_installation() {
    PHASE="final validation"
    supa.cc --version
    if supa.cc doctor --installation-check; then
        return 0
    fi
    warn "The software is installed, but the installation check reported a diagnostic. Resolve the diagnostic shown above before continuing."
    if ! tty_available; then
        fail "Resolve the diagnostic shown above and run 'supa.cc doctor --installation-check' again."
    fi
    prompt_installation_retry
    supa.cc doctor --installation-check || fail "Resolve the diagnostic shown above, then run 'supa.cc doctor --installation-check' again."
}

main() {
    parse_arguments "$@"
    PHASE="environment detection"
    detect_environment
    check_installation_channel
    build_plan
    print_plan
    confirm_plan

    if [ "$DRY_RUN" -eq 1 ]; then
        printf 'Dry run complete; no changes were made.\n'
        return 0
    fi

    make_temp_dir
    trap cleanup EXIT INT TERM
    if [ "$OS" = "macos" ]; then
        execute_macos
    else
        execute_linux
    fi
    verify_installation
    printf 'Supa.cc is ready.\n'
}

if [ -z "${BASH_SOURCE[0]:-}" ] || [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
