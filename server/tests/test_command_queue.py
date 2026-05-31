from app.command_queue import push_command, pop_pending, register_listener, unregister_listener


def test_push_and_pop_pending():
    pop_pending("queue-agent")
    push_command("queue-agent", "cmd-1")
    assert pop_pending("queue-agent") == ["cmd-1"]
    assert pop_pending("queue-agent") == []


def test_register_listener_flushes_pending():
    collected = []
    push_command("listener-agent", "cmd-listener")

    def on_command(command_id):
        collected.append(command_id)

    register_listener("listener-agent", on_command)
    assert collected == ["cmd-listener"]
    unregister_listener("listener-agent")
