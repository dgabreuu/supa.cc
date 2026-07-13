from supa_cc.ui.state import MenuAction, NavigationState, PageId


def test_navigation_state_defaults_to_home():
    state = NavigationState()
    assert state.current_page == PageId.HOME
    assert state.running is True


def test_open_navigates_to_subpage():
    state = NavigationState()
    state.open(PageId.SWITCH)
    assert state.current_page == PageId.SWITCH


def test_go_home_returns_to_home_page():
    state = NavigationState()
    state.open(PageId.ADD)
    state.go_home()
    assert state.current_page == PageId.HOME


def test_back_action_exists():
    assert MenuAction.BACK.value == "back"
