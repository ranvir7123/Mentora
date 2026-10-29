import QtQuick
import Theme
import "../components"

// The panel's top row: close the lesson, how far along it you are ("3 of 9"), and the sound switch.
Item {
    id: root
    property int stepIndex: 0           // the step you are on, from 0
    property int stepCount: 0
    property bool muted: false
    signal close()
    signal toggleSound()

    implicitHeight: 40

    IconButton {
        id: closeButton
        glyph: "cross"
        label: "Close the lesson"
        onClicked: root.close()
    }

    ProgressBar {
        anchors.left: closeButton.right
        anchors.right: soundButton.left
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space12
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -Theme.edge / 2      // level with the buttons' faces, not their edges
        value: root.stepCount > 0 ? Math.min(root.stepIndex, root.stepCount) / root.stepCount : 0
        label: root.stepCount > 0 ? Math.min(root.stepIndex + 1, root.stepCount) + " of " + root.stepCount : ""
    }

    IconButton {
        id: soundButton
        anchors.right: parent.right
        glyph: root.muted ? "muted" : "sound"
        label: root.muted ? "Turn sound on" : "Turn sound off"
        onClicked: root.toggleSound()
    }
}
