import QtQuick
import Theme

// The hints shown so far, numbered in the order they came, and a button for the next one while any are
// left. Shows nothing until the first hint is asked for (the Hint button sits in the help row).
Column {
    id: root
    property var hints: []
    property int hintsLeft: 0
    signal more()

    visible: hints.length > 0
    spacing: Theme.space8

    Repeater {
        model: root.hints
        delegate: Rectangle {
            required property string modelData
            required property int index

            width: root.width
            height: hintText.implicitHeight + 2 * Theme.space12
            radius: Theme.radiusMedium
            color: Theme.surface2
            Accessible.role: Accessible.StaticText
            Accessible.name: "Hint " + (index + 1) + ": " + modelData

            Text {
                id: number
                x: Theme.space12
                y: Theme.space12
                width: Theme.space16
                text: index + 1
                color: Theme.muted
                font.family: Theme.fontBody
                font.weight: Font.ExtraBold
                font.pixelSize: Theme.size16
            }

            Text {
                id: hintText
                x: number.x + number.width + Theme.space8
                y: Theme.space12
                width: parent.width - x - Theme.space12
                text: modelData
                wrapMode: Text.Wrap
                color: Theme.text
                font.family: Theme.fontBody
                font.pixelSize: Theme.size16
            }
        }
    }

    ChunkyButton {
        visible: root.hintsLeft > 0
        kind: "quiet"
        compact: true
        text: "Show another hint (" + root.hintsLeft + " left)"
        onClicked: root.more()
    }
}
