import QtQuick
import Theme
import "../components"

// The top of the home screen: hello and your name, your streak, today's points against the daily goal,
// and the sound switch.
Item {
    id: root
    property var learner: ({})
    property bool muted: false
    signal toggleSound()

    readonly property int streak: learner.streak || 0
    readonly property int points: learner.pointsToday || 0
    readonly property int goal: learner.dailyGoal || 0

    implicitHeight: 48

    Text {
        anchors.left: parent.left
        anchors.right: stats.left
        anchors.rightMargin: Theme.space24
        anchors.verticalCenter: parent.verticalCenter
        text: root.learner.name ? "Hi " + root.learner.name : "Hi there"
        elide: Text.ElideRight
        color: Theme.text
        font.family: Theme.fontHeading
        font.weight: Font.Bold
        font.pixelSize: Theme.size32
    }

    Row {
        id: stats
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.space32

        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.space8
            StreakFlame {
                anchors.verticalCenter: parent.verticalCenter
                days: root.streak
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.streak === 0 ? "Start a streak today"
                                        : root.streak === 1 ? "day in a row" : "days in a row"
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size14
            }
        }

        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.space12
            DailyRing {
                anchors.verticalCenter: parent.verticalCenter
                size: 40
                thickness: 5
                done: root.points
                goal: root.goal
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text {
                    text: root.points === 1 ? "1 point today" : root.points + " points today"
                    color: Theme.reward
                    font.family: Theme.fontBody
                    font.weight: Font.ExtraBold
                    font.pixelSize: Theme.size16
                }
                Text {
                    visible: root.goal > 0
                    text: "Your goal is " + root.goal
                    color: Theme.muted
                    font.family: Theme.fontBody
                    font.pixelSize: Theme.size14
                }
            }
        }

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: Theme.edge / 2      // its face, not its edge, lines up with the rest
            glyph: root.muted ? "muted" : "sound"
            label: root.muted ? "Turn sound on" : "Turn sound off"
            onClicked: root.toggleSound()
        }
    }
}
