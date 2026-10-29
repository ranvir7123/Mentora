import QtQuick
import Theme
import "../components"

// What the finished lesson earned. Once `start()` runs, the results fill in one by one, 250 ms apart:
// points, time, right first try, then the streak ticks up by one.
Card {
    id: root
    property var complete: ({ "points": 0, "seconds": 0, "firstTry": 0, "steps": 0, "streak": 0 })
    property int filled: 0              // how many rows have filled in

    function start() {
        filled = 0
        fill.restart()
    }
    function clock(seconds) {
        const total = Math.round(seconds)
        const s = total % 60
        return Math.floor(total / 60) + ":" + (s < 10 ? "0" + s : s)
    }

    Timer {
        id: fill
        interval: 250
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            root.filled += 1
            if (root.filled >= 4)
                stop()
        }
    }

    spacing: Theme.space4
    Accessible.role: Accessible.Grouping
    Accessible.name: "What you earned"

    component Result: Item {
        id: row
        property bool shown: false
        property string label: ""
        property string value: ""
        property color colour: Theme.text
        default property alias extra: slot.data

        width: parent.width
        height: 48
        opacity: shown ? 1 : 0
        scale: shown ? 1 : 0.92
        Behavior on opacity { NumberAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }
        Accessible.role: Accessible.StaticText
        Accessible.name: label + ": " + value

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: row.label
            color: Theme.text
            font.family: Theme.fontBody
            font.weight: Font.Bold
            font.pixelSize: Theme.size16
        }
        Text {
            visible: row.value !== ""
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: row.value
            color: row.colour
            font.family: Theme.fontBody
            font.weight: Font.ExtraBold
            font.pixelSize: Theme.size24
        }
        Item {
            id: slot
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: childrenRect.width
            height: childrenRect.height
        }
    }

    Result {
        shown: root.filled > 0
        label: "Points"
        value: root.complete.points
        colour: Theme.reward
    }
    Result {
        shown: root.filled > 1
        label: "Time"
        value: root.clock(root.complete.seconds)
    }
    Result {
        shown: root.filled > 2
        label: "Right first try"
        value: root.complete.firstTry + " of " + root.complete.steps
        colour: Theme.right
    }
    Result {
        id: streakRow
        shown: root.filled > 3
        label: "Days in a row"

        StreakFlame {
            id: flame
            // One less until the row fills in, then it ticks up and the flame pops.
            days: streakRow.shown ? root.complete.streak : Math.max(0, root.complete.streak - 1)
            size: 28
            transformOrigin: Item.Center
            onDaysChanged: if (streakRow.shown) pop.restart()
            SequentialAnimation {
                id: pop
                NumberAnimation { target: flame; property: "scale"; to: 1.2; duration: Theme.durFast; easing.type: Easing.OutCubic }
                NumberAnimation { target: flame; property: "scale"; to: 1; duration: Theme.durNormal; easing.type: Easing.OutCubic }
            }
        }
    }
}
