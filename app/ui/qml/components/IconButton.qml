import QtQuick
import Theme

// A square quiet chunky button showing one glyph (close, sound, muted). `label` is what a screen reader
// says, since there are no words on it.
Item {
    id: root
    property string glyph: "cross"
    property string label: ""
    property bool held: false
    signal clicked()

    readonly property bool down: (area.pressed || held) && enabled

    implicitWidth: 40
    implicitHeight: 40
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.onPressAction: root.clicked()
    Keys.onSpacePressed: root.clicked()
    Keys.onReturnPressed: root.clicked()

    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

    Rectangle {
        y: Theme.edge
        width: parent.width
        height: parent.height - Theme.edge
        radius: Theme.radiusMedium
        color: Theme.border
    }

    Rectangle {
        width: parent.width
        height: parent.height - Theme.edge
        y: root.down ? Theme.edge : 0
        radius: Theme.radiusMedium
        color: Theme.surface2
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.text
        Behavior on y { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

        Glyph {
            anchors.centerIn: parent
            name: root.glyph
            colour: Theme.text
            size: 20
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
