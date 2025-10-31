from dataclasses import dataclass

from textual.app import ComposeResult
from textual.layout import Layout
from textual.layouts.grid import GridLayout
from textual.widget import Widget
from textual import containers
from textual import widgets
from textual.message import Message
from textual.reactive import var


class SideBar(containers.Vertical):
    BINDINGS = [("escape", "dismiss", "Dismiss sidebar")]
    DEFAULT_CSS = """
    SideBar {
        height: 1fr;         
        layout: vertical;
        overflow: hidden scroll;
        scrollbar-size: 0 0;

        Collapsible {                   
            height: 1fr;              
            min-height: 3;

            &.-collapsed {
                height: auto;
            }

            &.-fixed {                
                height: auto;
            }
                                
            Contents {
                height: auto;
                padding: 0;
                margin: 1 0 0 0;                
            }
        }
    }
    """

    class Dismiss(Message):
        pass

    @dataclass(frozen=True)
    class Panel:
        title: str
        widget: Widget
        flex: bool = False
        collapsed: bool = False
        id: str | None = None

    def __init__(
        self,
        *panels: Panel,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
        hide: bool = False,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.panels: list[SideBar.Panel] = [*panels]
        self.hide = hide

    def compose(self) -> ComposeResult:
        for panel in self.panels:
            yield widgets.Collapsible(
                panel.widget,
                title=panel.title,
                collapsed=panel.collapsed,
                classes="-flex" if panel.flex else "-fixed",
                id=panel.id,
            )

    def action_dismiss(self) -> None:
        self.post_message(self.Dismiss())


if __name__ == "__main__":
    from textual.app import App, ComposeResult

    class SApp(App):
        def compose(self) -> ComposeResult:
            yield SideBar(
                SideBar.Panel("Hello", widgets.Label("Hello, World!")),
                SideBar.Panel(
                    "Files",
                    widgets.DirectoryTree(
                        "~/",
                    ),
                    flex=True,
                ),
                SideBar.Panel(
                    "Hello",
                    widgets.Static("Where there is a Will! " * 10),
                ),
            )

    SApp().run()
