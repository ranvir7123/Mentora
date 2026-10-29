import QtQuick
import QtQuick.Window
import Theme

Window {
    id: root
    required property var bridge
    readonly property var lesson: bridge.lesson

    width: 360
    height: Screen.desktopAvailableHeight
    x: Screen.virtualX + Screen.desktopAvailableWidth - width
    y: Screen.virtualY
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    visible: root.lesson.open
    color: Theme.bg
    title: "Project X lesson"
}
