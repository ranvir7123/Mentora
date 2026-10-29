import QtQuick
import QtQuick.Window
import Theme

Window {
    id: root
    required property var bridge
    readonly property var pointer: bridge.pointer

    x: Screen.virtualX
    y: Screen.virtualY
    width: Screen.width
    height: Screen.height
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
           | Qt.WindowDoesNotAcceptFocus | Qt.Tool
    visible: root.pointer.visible
    color: Theme.clear
    title: "Project X pointer"
}
