import QtQuick
import Theme
import "../components"
import "../mascot"

// The biggest thing on the home screen: the lesson you are part way through ("Monthly budget, step 4 of
// 9") and one button to carry on. With nothing started yet it offers your first lesson instead. The
// mascot sits on the button, waiting for you.
Rectangle {
    id: root
    property var card: null             // the continue card from the backend, or null
    property var first: null            // {id, title, courseTitle}: the lesson to start with on a first run
    property string courseTitle: ""     // the course the lesson in progress belongs to
    signal continueLesson()
    signal start(string lessonId)

    readonly property bool resuming: card !== null && card !== undefined
    readonly property real pad: Theme.space32

    visible: resuming || (first !== null && first !== undefined)
    implicitHeight: Math.max(words.implicitHeight, perch.height + button.height) + 2 * pad
    radius: Theme.radiusLarge
    color: Theme.surface1

    Column {
        id: words
        x: root.pad
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - 2 * root.pad - button.width - Theme.space32
        spacing: Theme.space12

        Text {
            width: parent.width
            text: root.resuming ? root.card.title + ", step " + root.card.step + " of " + root.card.of
                                : root.first ? "Start with " + root.first.title : ""
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            color: Theme.text
            font.family: Theme.fontHeading
            font.weight: Font.Bold
            font.pixelSize: Theme.size32
        }
        Text {
            width: parent.width
            text: root.resuming ? (root.courseTitle ? "Pick up where you left off in " + root.courseTitle + "."
                                                    : "Pick up where you left off.")
                                : root.first ? "Your first " + root.first.courseTitle + " lesson." : ""
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            color: Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
        }
        Item {
            visible: root.resuming
            width: parent.width
            height: Theme.space4
        }
        ProgressBar {
            visible: root.resuming
            width: Math.min(parent.width, 360)
            value: root.resuming && root.card.of > 0 ? (root.card.step - 1) / root.card.of : 0
        }
    }

    ChunkyButton {
        id: button
        anchors.right: parent.right
        anchors.rightMargin: root.pad
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.pad
        width: 176
        height: 56
        text: root.resuming ? "Continue" : "Start"
        onClicked: root.resuming ? root.continueLesson() : root.start(root.first.id)
    }

    Mascot {
        id: perch
        size: 56
        anchors.horizontalCenter: button.horizontalCenter
        anchors.bottom: button.top
        anchors.bottomMargin: -Theme.space4            // its feet rest on the button's face
    }
}
