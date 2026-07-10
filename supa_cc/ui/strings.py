# Centralização de todos os textos da aplicação

class UIStrings:
    """Textos da interface TUI."""

    # Home
    APP_NAME = "Supa.cc"
    APP_DESCRIPTION = "Gerenciamento local de contas Supabase com segurança."
    APP_SUBTITLE = "Quem é você hoje?"
    PANEL_TITLE = "Supa.cc"
    ACCOUNT_COUNT_ONE = "conta salva"
    ACCOUNT_COUNT_MANY = "contas salvas"

    # Menu
    MENU_TITLE = "Escolha uma ação:"
    MENU_ADD = "Adicionar conta"
    MENU_LIST = "Listar contas"
    MENU_SWITCH = "Alternar conta ativa"
    MENU_REMOVE = "Remover conta"
    MENU_BACK = "Voltar"
    MENU_EXIT = "Sair"

    # Prompts
    PROMPT_ACCOUNT_NAME = "Nome da conta:"
    PROMPT_ACCESS_TOKEN = "Token de acesso:"
    PROMPT_LIST_ACCOUNTS = "Contas cadastradas:"
    PROMPT_SELECT_ACCOUNT = "Selecione a conta:"
    PROMPT_SELECT_REMOVE = "Selecione a conta para remover:"
    PROMPT_CONFIRM_REMOVE = "Remover conta '{}'?"

    # Mensagens de feedback
    MSG_ACCOUNT_ADDED = "Conta '{}' adicionada."
    MSG_ACCOUNT_REQUIRED = "Nome da conta é obrigatório."
    MSG_TOKEN_REQUIRED = "Token de acesso é obrigatório."
    MSG_NO_ACCOUNTS = "Nenhuma conta cadastrada."
    MSG_NO_ACCOUNTS_SWITCH = "Nenhuma conta para alternar."
    MSG_NO_ACCOUNTS_REMOVE = "Nenhuma conta para remover."
    MSG_LISTED_ACCOUNTS = "Listadas {} {}."
    MSG_SWITCH_CANCELLED = "Alternância de conta cancelada."
    MSG_REMOVE_CANCELLED = "Remoção de conta cancelada."
    MSG_ACCOUNT_ACTIVATED = "Conta '{}' ativada."
    MSG_ACTIVATE_FAILED = "Falha ao ativar conta '{}'."
    MSG_ACCOUNT_REMOVED = "Conta '{}' removida."
    MSG_UNKNOWN_OPTION = "Opção de menu desconhecida."
    MSG_GOODBYE = "Até logo!"

    # Loading
    LOADING_SWITCH_ACCOUNT = "Ativando conta..."

    # Tabela de contas
    TABLE_TITLE = "Contas cadastradas"
    TABLE_STATUS = "Status"
    TABLE_ACCOUNT = "Conta"
    STATUS_ACTIVE = "Ativa"
    STATUS_AVAILABLE = "Disponível"

    # Sufixos
    ACCOUNT_SUFFIX_ONE = "conta"
    ACCOUNT_SUFFIX_MANY = "contas"


class CLIStrings:
    """Textos do CLI não-interativo."""

    APP_DESCRIPTION = "Supa.cc - Gerenciamento local de contas Supabase"
    CMD_ADD_HELP = "Adicionar nova conta."
    CMD_LIST_HELP = "Listar contas cadastradas."
    CMD_SWITCH_HELP = "Alternar conta ativa."
    CMD_REMOVE_HELP = "Remover conta cadastrada."
    MSG_ACCOUNT_ADDED = "Conta '{}' adicionada."
    MSG_ERROR = "Erro: {}"
    MSG_NO_ACCOUNTS = "Nenhuma conta cadastrada."
    MSG_ACCOUNT_ACTIVATED = "Conta '{}' ativada."
    MSG_ACTIVATE_FAILED = "Falha ao ativar conta '{}'."
    MSG_ACCOUNT_REMOVED = "Conta '{}' removida."
    MSG_CONFIRM_REMOVE = "Remover conta?"
