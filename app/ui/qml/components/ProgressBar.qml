import QtQuick
import Theme

// How far along something is, with an optional label such as "3 of 9" at its right end. Given a count of
// `segments` (the steps of a lesson), it is a row of short strokes, one per step: the done ones filled in
// yellow, the one you are on outlined. Too many to tell apart, and it is one plain bar.
Item {
    id: root
    property real value: 0
    property string label: ""
    property int segments: 0

    readonly property real clamped: Math.max(0, Math.min(1, value))
    readonly property real gap: 3
    readonly property bool split: segments > 1
                                  && (track.width - gap * (segments - 1)) / segments >= 8
    readonly property int filled: Math.round(clamped * segments)

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
        height: 10
        radius: Theme.radiusSmall
        color: root.split ? Theme.clear : Theme.surface2

        Rectangle {
            height: parent.height
            radius: parent.radius
            color: Theme.accent
            visible: !root.split && root.clamped > 0
            width: Math.max(parent.height, parent.width * root.clamped)
            Behavior on width { NumberAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }
        }

        Row {
            visible: root.split
            spacing: root.gap
            Repeater {
                model: root.split ? root.segments : 0
                delegate: Rectangle {
                    required property int index
                    width: (track.width - root.gap * (root.segments - 1)) / root.segments
                    height: track.height
                    radius: Theme.radiusSmall
                    color: index < root.filled ? Theme.accent : Theme.surface2
                    border.width: index === root.filled ? 2 : 0
                    border.color: Theme.accent
                    Behavior on color { ColorAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }
                }
            }
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
