import traceback # noqa: N999

from base_plugin import BasePlugin, HookResult # noqa: N999
from android_utils import log # noqa: N999
from . import Main # noqa: N999
# pyright: reportMissingImports=false

class pic2gifMain(BasePlugin):
    def on_plugin_load(self):
        self.add_on_send_message_hook()
        log("p2g: plugin loaded")

    def on_plugin_unload(self):
        log("p2g: plugin unloaded")

    def on_send_message_hook(self, account, params) -> HookResult:
        # this hook sits on the app's send path: letting an exception escape
        # would break sending ordinary messages, so it never propagates
        try:
            return Main.handleSendMessageHook(params)
        except Exception as e:
            log(f"p2g: send message hook failed: {e}")
            log(traceback.format_exc())
            return HookResult()
