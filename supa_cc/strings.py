# Centralized application text.

class CommonStrings:
    """Text shared by the CLI and TUI."""

    MSG_ACCOUNT_ADDED = "Account '{}' added."
    MSG_ACCOUNT_REMOVED = "Account '{}' removed."
    MSG_NO_ACCOUNTS = "No accounts registered."


class UIStrings(CommonStrings):
    """Text for the TUI."""

    # Home
    APP_NAME = "Supa.cc"
    APP_DESCRIPTION = "Secure local management for Supabase accounts."
    ACCOUNT_COUNT_ONE = "saved account"
    ACCOUNT_COUNT_MANY = "saved accounts"
    ACTIVE_ACCOUNT = "Active"
    ACTIVE_ACCOUNT_NONE = "not selected"

    # Menu
    MENU_TITLE = "Choose an action:"
    MENU_ADD = "Add account"
    MENU_SWITCH = "Switch active account"
    MENU_REMOVE = "Remove account"
    MENU_BACK = "Back"
    MENU_EXIT = "Exit"

    # Prompts
    PROMPT_ACCOUNT_NAME = "Account name:"
    PROMPT_ACCESS_TOKEN = "Access token:"
    PROMPT_SELECT_ACCOUNT = "Select an account:"
    PROMPT_SELECT_REMOVE = "Select an account to remove:"
    PROMPT_CONFIRM_REMOVE = "Remove account '{}'?"

    # Feedback messages
    MSG_ACCOUNT_REQUIRED = "Account name is required."
    MSG_TOKEN_REQUIRED = "Access token is required."
    MSG_NO_ACCOUNTS_SWITCH = "No accounts available to switch."
    MSG_NO_ACCOUNTS_REMOVE = "No accounts available to remove."
    MSG_UNKNOWN_OPTION = "Unknown menu option."
    MSG_GOODBYE = "Goodbye!"

    # Loading
    LOADING_SWITCH_ACCOUNT = "Activating account… (up to 30s)"



class CLIStrings(CommonStrings):
    """Text for the non-interactive CLI."""

    APP_DESCRIPTION = "Supa.cc - Local Supabase account management"
    CMD_ADD_HELP = "Add a new account."
    CMD_LIST_HELP = "List registered accounts."
    CMD_SWITCH_HELP = "Switch the active account."
    CMD_REMOVE_HELP = "Remove a registered account."
    MSG_ERROR = "Error: {}"
    MSG_CONFIRM_REMOVE = "Remove account?"
    PROMPT_ACCESS_TOKEN = "Access token"
