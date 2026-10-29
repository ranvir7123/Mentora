import QtQuick
import Theme

// One lesson on a course's path: a chunky circle with its title and badge under it.
// state "done" shows a tick, "current" its number with a soft pulsing halo, "locked" a dim lock.
Item {
    id: root
    property string title: ""
    property string badge: ""
    property int number: 1
    signal clicked()

    states: [State { name: "done" }, State { name: "current" }, State { name: "locked" }]
    state: "locked"

    readonly property bool open: state !== "locked"
    readonly property real circle: 72
    readonly property real lift: 6
    readonly property bool down: area.pressed && open

    implicitWidth: 136
    implicitHeight: circle + lift + Theme.space8 + words.implicitHeight
    activeFocusOnTab: open
    Accessible.role: Accessible.Button
    Accessible.name: title + (state === "done" ? ", done" : state === "current" ? ", up next" : ", locked")
    Accessible.onPressAction: if (open) root.clicked()
    Keys.onSpacePressed: if (open) root.clicked()
    Keys.onReturnPressed: if (open) root.clicked()

    Item {
        id: button
        width: root.circle
        height: root.circle + root.lift
        anchors.horizontalCenter: parent.horizontalCenter

        // The halo: a thin steady ring 8 px clear of the circle and its edge, and a copy that swells
        // and fades now and then.
        Rectangle {
            id: halo
            visible: root.state === "current"
            anchors.centerIn: parent
            width: root.circle + root.lift + 2 * (Theme.space8 + 3)
            height: width
            radius: width / 2
            color: Theme.clear
            border.width: 3
            border.color: Theme.accent
        }
        Rectangle {
            id: pulse
            visible: root.state === "current"
            anchors.centerIn: parent
            width: halo.width
            height: width
            radius: width / 2
            color: Theme.clear
            border.width: 3
            border.color: Theme.accent
            opacity: 0
            SequentialAnimation {
                running: root.state === "current" && root.visible
                loops: Animation.Infinite
                ParallelAnimation {
                    NumberAnimation { target: pulse; property: "scale"; from: 1; to: 1.18; duration: 500; easing.type: Easing.OutCubic }
                    NumberAnimation { target: pulse; property: "opacity"; from: 0.5; to: 0; duration: 500; easing.type: Easing.OutCubic }
                }
                PauseAnimation { duration: 1100 }
            }
        }

        Rectangle {
            y: root.lift
            width: root.circle
            height: root.circle
            radius: width / 2
            color: root.open ? Theme.accentEdge : Theme.border
        }

        Rectangle {
            id: face
            y: root.down ? root.lift : 0
            width: root.circle
            height: root.circle
            radius: width / 2
            color: root.open ? Theme.accent : Theme.surface2
            border.width: root.activeFocus ? 2 : 0
            border.color: Theme.text
            Behavior on y { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

            Glyph {
                visible: root.state === "done"
                anchors.centerIn: parent
                name: "tick"
                colour: Theme.onColour
                size: 36
                stroke: 4
            }
            Text {
                visible: root.state === "current"
                anchors.centerIn: parent
                text: root.number
                color: Theme.onColour
                font.family: Theme.fontBody
                font.weight: Font.ExtraBold
                font.pixelSize: Theme.size24
            }
            Glyph {
                visible: root.state === "locked"
                anchors.centerIn: parent
                name: "lock"
                colour: Theme.muted
                size: 28
                stroke: 2.6
            }
        }

        MouseArea {
            id: area
            anchors.fill: parent
            enabled: root.open
            cursorShape: Qt.PointingHandCursor
            onClicked: root.clicked()
        }
    }

    Column {
        id: words
        y: button.height + Theme.space8
        width: parent.width
        Text {
            width: parent.width
            text: root.title
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            color: root.open ? Theme.text : Theme.muted
            font.family: Theme.fontBody
            font.weight: Font.Bold
            font.pixelSize: Theme.size14
        }
        Text {
            visible: root.badge !== ""
            width: parent.width
            text: root.badge
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            color: Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size12
        }
    }
}
