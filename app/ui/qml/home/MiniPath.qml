import QtQuick
import Theme
import "../components"

// A course's lessons in miniature, the way its path draws them: ticked coral dots for the lessons you have
// done, a ringed one for the lesson you are on, then quiet ones, all on one line. With many lessons the
// dots draw closer and smaller; `fits` turns false once they would crowd each other, for a plain bar instead.
Item {
    id: root
    property var lessons: []

    readonly property int count: lessons.length
    readonly property int current: lessons.findIndex(l => l.state === "current")
    readonly property int reached: {                    // the last lesson you can open
        let last = -1
        for (let i = 0; i < count; ++i)
            if (lessons[i].state !== "locked")
                last = i
        return last
    }

    readonly property real room: 14                     // half the widest ring, kept free at each end
    readonly property real step: count > 1 ? Math.min(48, (width - 2 * room) / (count - 1)) : 0
    readonly property bool fits: count < 2 || step >= 14
    readonly property real dot: count > 1 ? Math.min(20, step - 6) : 20

    implicitWidth: 2 * room + Math.max(0, count - 1) * 48
    implicitHeight: 2 * room

    function middle(i) {
        return room + i * step
    }

    // The line: coral up to the last lesson you can open, quiet after it.
    Rectangle {
        visible: root.count > 1
        x: root.middle(0)
        width: root.middle(root.count - 1) - x
        anchors.verticalCenter: parent.verticalCenter
        height: 4
        radius: 2
        color: Theme.surface2
    }
    Rectangle {
        visible: root.reached > 0
        x: root.middle(0)
        width: root.middle(root.reached) - x
        anchors.verticalCenter: parent.verticalCenter
        height: 4
        radius: 2
        color: Theme.accent
    }

    Repeater {
        model: root.count
        delegate: Rectangle {
            required property int index
            readonly property string kind: root.lessons[index].state
            x: root.middle(index) - width / 2
            anchors.verticalCenter: parent.verticalCenter
            width: root.dot
            height: width
            radius: width / 2
            color: index <= root.reached ? Theme.accent : Theme.surface2
            Glyph {
                visible: parent.kind === "done" && root.dot >= 14
                anchors.centerIn: parent
                name: "tick"
                colour: Theme.onColour
                size: root.dot * 0.7
                stroke: 3.5
            }
        }
    }

    // The lesson you are on.
    Rectangle {
        visible: root.current >= 0
        x: root.middle(Math.max(0, root.current)) - width / 2
        anchors.verticalCenter: parent.verticalCenter
        width: root.dot + 8
        height: width
        radius: width / 2
        color: Theme.clear
        border.width: 2
        border.color: Theme.accent
    }
}
