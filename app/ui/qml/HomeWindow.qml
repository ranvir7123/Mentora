import QtQuick
import QtQuick.Window
import Theme

Window {
    id: root
    required property var bridge
    readonly property var home: bridge.home

    width: 1120
    height: 720
    visible: true
    color: Theme.bg
    title: "Project X"

    Text {
        x: Theme.space48
        y: Theme.space48
        text: root.home.learner.name ? "Hi " + root.home.learner.name : "Hi there"
        color: Theme.text
        font.family: Theme.fontHeading
        font.weight: Font.Bold
        font.pixelSize: Theme.size32
    }
}
