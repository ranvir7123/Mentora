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
    implicitHeight: words.implicitHeight + Theme.space48 + foot.height + 2 * pad      // room for the mascot
    radius: Theme.radiusLarge
    color: Theme.surface1

    // The lesson's name across the whole card in the wide cut, so it reads first and in one line.
    Column {
        id: words
        x: root.pad
        y: root.pad
        width: parent.width - 2 * root.pad
        spacing: Theme.space8

        Text {
            width: parent.width
            text: root.resuming ? root.card.title + ", step " + root.card.step + " of " + root.card.of
                                : root.first ? "Start with " + root.first.title : ""
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            lineHeight: 1.05
            color: Theme.text
            font.family: Theme.fontDisplay
            font.weight: Font.ExtraBold
            font.letterSpacing: Theme.tightDisplay
            font.pixelSize: Theme.size32
        }
        Text {
            width: parent.width - button.width - Theme.space24     // clear of the mascot on the button
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
    }

    // The foot: how far along the lesson is, and the one button to carry on.
    Item {
        id: foot
        x: root.pad
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.pad
        width: parent.width - 2 * root.pad
        height: button.height

        ProgressBar {
            visible: root.resuming
            anchors.left: parent.left
            anchors.right: button.left
            anchors.rightMargin: Theme.space32
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -Theme.edge / 2      // level with the button's face
            value: root.resuming && root.card.of > 0 ? (root.card.step - 1) / root.card.of : 0
            segments: root.resuming ? root.card.of : 0
        }

        ChunkyButton {
            id: button
            anchors.right: parent.right
            width: 176
            height: 56
            text: root.resuming ? "Continue" : "Start"
            onClicked: root.resuming ? root.continueLesson() : root.start(root.first.id)
        }
    }

    Mascot {
        id: perch
        size: 56
        x: foot.x + button.x + (button.width - width) / 2
        anchors.bottom: foot.top
        anchors.bottomMargin: -Theme.space4            // its feet rest on the button's face
    }
}
