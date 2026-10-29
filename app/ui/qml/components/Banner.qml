import QtQuick
import Theme

// The message that slides up over the bottom of the panel: right (mint), not yet (rose and gentle, no
// shake), a step that came undone (a coral link), the app closed (the main button) or an error.
// A right banner says one of a few words, picked by `turn` so the panel can vary it step by step.
Item {
    id: root
    property string kind: "right"
    property string text: ""
    property string actionText: ""
    property bool shown: true
    property int turn: 0
    signal action()

    readonly property var rightWords: ["Nailed it!", "That's it!", "Spot on!", "You got it!"]
    readonly property string heading: kind === "right" ? rightWords[Math.abs(turn) % rightWords.length]
                                      : kind === "not_yet" ? "Not yet" : ""
    readonly property color tint: kind === "right" ? Theme.rightTint
                                  : kind === "not_yet" ? Theme.notYetTint : Theme.surface2
    // Lesson lines start "Not yet: …"; the heading already says it, so the line drops it.
    readonly property string bare: kind === "not_yet" ? text.replace(/^\s*not yet\s*[:,.!-]?\s*/i, "") : text
    readonly property string body: bare.charAt(0).toUpperCase() + bare.slice(1)
    // Where the heading's middle sits, so the panel can float +10 level with it.
    readonly property real headingCentre: lines.y + headingRow.height / 2
    // How much of the banner is on screen right now, following the slide, so the panel can make room.
    readonly property real reach: Math.max(0, height - slide.y)

    implicitWidth: 360
    implicitHeight: lines.implicitHeight + 2 * Theme.space16
    Accessible.role: Accessible.AlertMessage
    Accessible.name: heading !== "" ? heading + " " + body : body

    Rectangle {
        id: sheet
        width: parent.width
        height: parent.height
        color: root.tint
        topLeftRadius: Theme.radiusLarge
        topRightRadius: Theme.radiusLarge
        opacity: root.shown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }
        transform: Translate {
            id: slide
            y: root.shown ? 0 : sheet.height
            Behavior on y { NumberAnimation { duration: Theme.durNormal; easing.type: Easing.OutCubic } }
        }

        Column {
            id: lines
            x: Theme.space16
            y: Math.max(Theme.space16, Math.round((parent.height - height) / 2))   // centred when the banner is taller
            width: parent.width - 2 * Theme.space16
            spacing: Theme.space8

            Row {
                id: headingRow
                visible: root.heading !== ""
                spacing: Theme.space8
                Glyph {
                    visible: root.kind === "right"
                    anchors.verticalCenter: parent.verticalCenter
                    name: "tick"
                    colour: Theme.right
                    size: 24
                    stroke: 3.2
                }
                Text {
                    text: root.heading
                    color: root.kind === "right" ? Theme.right : Theme.notYet
                    font.family: Theme.fontHeading
                    font.weight: Font.Bold
                    font.pixelSize: Theme.size24
                }
            }

            Item {
                visible: root.body !== ""
                width: parent.width
                height: words.implicitHeight
                Glyph {
                    id: errorMark
                    visible: root.kind === "error"
                    y: 1
                    name: "cross"
                    colour: Theme.notYet
                    size: 20
                    stroke: 3
                }
                Text {
                    id: words
                    x: errorMark.visible ? errorMark.width + Theme.space8 : 0
                    width: parent.width - x
                    text: root.body
                    wrapMode: Text.Wrap
                    color: Theme.text
                    font.family: Theme.fontBody
                    font.weight: root.heading === "" ? Font.Bold : Font.Normal
                    font.pixelSize: Theme.size16
                }
            }

            Item {
                visible: button.visible
                width: 1
                height: Theme.space4
            }

            ChunkyButton {
                id: button
                visible: root.actionText !== "" && root.kind !== "changed"
                width: parent.width
                text: root.actionText
                // On surface2 a quiet button would vanish, so the one way out of a stop is the main button.
                kind: root.kind === "right" ? "right" : root.kind === "not_yet" ? "quiet" : "main"
                onClicked: root.action()
            }

            Text {
                id: link
                visible: root.actionText !== "" && root.kind === "changed"
                text: root.actionText
                color: Theme.accent
                font.family: Theme.fontBody
                font.weight: Font.ExtraBold
                font.pixelSize: Theme.size16
                font.underline: linkArea.containsMouse || link.activeFocus
                activeFocusOnTab: true
                Accessible.role: Accessible.Link
                Accessible.name: text
                Accessible.onPressAction: root.action()
                Keys.onSpacePressed: root.action()
                Keys.onReturnPressed: root.action()

                MouseArea {
                    id: linkArea
                    anchors.fill: parent
                    anchors.margins: -Theme.space8
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.action()
                }
            }
        }
    }
}
