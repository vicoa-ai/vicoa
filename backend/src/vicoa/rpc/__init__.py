"""Daemon-side RPC handlers.

Each module here implements one RPC method family (file ops, git ops, …). The
`MachineDaemon` dispatches to them from `_handle_rpc_request` and registers
their names in its `rpc-register` payload at WS connect time.
"""
