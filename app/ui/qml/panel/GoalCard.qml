import QtQuick
import Theme
import "../components"

// What you'll make: a picture of the finished result and one sentence. It opens the lesson; after the first
// step it folds away to a one-line chip (GoalChip), and a tap here folds it again.
Item {
    id: root
    property var goal: ({ "sentence": "", "picture": null })
    property bool foldable: false
    signal fold()

    readonly property string picture: goal && goal.picture ? goal.picture : ""

    implicitWidth: 328
    implicitHeight: card.implicitHeight
    Accessible.role: Accessible.Grouping
    Accessible.name: "Your goal: " + sentence.text

    Card {
        id: card
        width: parent.width
        spacing: Theme.space12

        Rounded {
            visible: root.picture !== "" && image.status === Image.Ready
            width: parent.width
            height: image.implicitWidth > 0 ? Math.round(width * Math.min(image.implicitHeight / image.implicitWidth, 0.75)) : 0
            Image {
                id: image
                anchors.fill: parent
                source: root.picture !== "" ? "file:///" + root.picture.replace(/\\/g, "/") : ""
                fillMode: Image.PreserveAspectCrop
                smooth: true
                mipmap: true
            }
        }

        Text {
            id: sentence
            width: parent.width
            text: root.goal ? root.goal.sentence : ""
            wrapMode: Text.Wrap
            color: Theme.text
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.foldable
        cursorShape: Qt.PointingHandCursor
        Accessible.role: Accessible.Button
        Accessible.name: "Fold your goal away"
        onClicked: root.fold()
    }
}
