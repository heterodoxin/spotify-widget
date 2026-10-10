from spotify_widget.hotkey import DEFAULT, MAC_KEYS, parse


def test_default_is_control_super_l():
    assert parse(DEFAULT) == (frozenset({'ctrl', 'super'}), 'l')


def test_modifier_names_from_every_system_are_understood():
    assert parse('Cmd+Option+K') == (frozenset({'super', 'alt'}), 'k')
    assert parse('win + shift + f9') == (frozenset({'super', 'shift'}), 'f9')
    assert parse('control+alt+7') == (frozenset({'ctrl', 'alt'}), '7')


def test_anything_else_claims_no_key():
    for text in ('none', '', 'l', 'ctrl+', 'ctrl+f13', 'hyper+l', 'ctrl+space', 'ctrl+é'):
        assert parse(text) is None


def test_mac_key_codes_match_the_ansi_layout():
    assert [MAC_KEYS[key] for key in ('a', 'b', 'q', 't', '1', '0', 'p', 'l', 'm', 'f1', 'f12')] == \
        [0, 11, 12, 17, 18, 29, 35, 37, 46, 122, 111]
    assert len(set(MAC_KEYS.values())) == len(MAC_KEYS)
