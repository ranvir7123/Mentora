import QtQuick
import Theme

// A thick rounded coral bar with an optional label such as "3 of 9" at its right end.
Item {
    id: root
    property real value: 0
    property string label: ""

    readonly property real clamped: Math.max(0, Math.min(1, value))

    implicitWidth: 240
    implicitHeight: Math.max(12, labelText.implicitHeight)
    Accessible.role: Accessible.ProgressBar
    Accessible.name: label

    Rectangle {
        id: track
        anchors.left: parent.left
        anchors.right: labelText.visible ? labelText.left : parent.right
        anchors.rightMargin: labelText.visible ? Theme.space12 : 0
        anchors.verticalCenter: parent.verticalCenter
        height: 12
        radius: Theme.radiusSmall
        color: Theme.surface2

        Rectangle {
            height: parent.height
            radius: parent.radius
            color: Theme.accent
            visible: root.clamped > 0
            width: Math.max(parent.height, parent.width * root.clamped)
            Behavior on width { NumberAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }
        }
    }

    Text {
        id: labelText
        visible: root.label !== ""
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: root.label
        color: Theme.muted
        font.family: Theme.fontBody
        font.weight: Font.Bold
        font.pixelSize: Theme.size14
    }
}
