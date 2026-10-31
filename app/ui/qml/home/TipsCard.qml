import QtQuick
import Theme

// Two or three plain sentences Meta's AI (or Claude, when `ai` says so) wrote from how your lessons went. While they are being written,
// a calm placeholder shows, but only after 200 ms, so a quick answer never flickers. With no finished
// lesson it says how to get tips; when the AI can't be reached it says lessons still work.
// No box: a note in the margin, under a ruled line, so it reads quieter than the things you can press.
Rectangle {
    id: root
    property var tips: ({})
    property string ai: "meta"          // or "claude", when MENTORA_AI=claude

    readonly property string kind: tips.state || "none"
    readonly property real pad: Theme.space16

    implicitHeight: words.implicitHeight + pad
    color: Theme.clear

    Rectangle {
        width: parent.width
        height: Theme.hairline
        color: Theme.border
    }

    // Loading that lasts past 200 ms.
    property bool slow: false
    onKindChanged: {
        slow = false
        if (kind === "loading")
            wait.restart()
    }
    Component.onCompleted: if (kind === "loading") wait.restart()
    Timer { id: wait; interval: 200; onTriggered: root.slow = root.kind === "loading" }

    Column {
        id: words
        y: root.pad
        width: parent.width
        spacing: Theme.space8

        // The heading, with who wrote the tips at the other end of the line.
        Item {
            width: parent.width
            height: heading.implicitHeight
            Text {
                id: heading
                text: "Tips for you"
                color: Theme.text
                font.family: Theme.fontHeading
                font.weight: Font.ExtraBold
                font.pixelSize: Theme.size20
            }
            Text {
                visible: root.kind === "ready"
                anchors.right: parent.right
                anchors.left: heading.right
                anchors.leftMargin: Theme.space12
                anchors.baseline: heading.baseline
                horizontalAlignment: Text.AlignRight
                text: root.ai === "claude" ? "From Claude" : "From Meta's AI"
                elide: Text.ElideRight
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size12
            }
        }

        Text {
            visible: root.kind !== "loading"
            width: parent.width
            text: root.kind === "ready" ? root.tips.text || ""
                  : root.kind === "error" ? (root.ai === "claude" ? "Claude" : "Meta") + " can't be reached right now. Lessons still work."
                  : "Finish a lesson to get tips"
            wrapMode: Text.Wrap
            lineHeight: 1.15
            color: root.kind === "ready" ? Theme.text : Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
        }

        // The placeholder keeps its room from the start, so the card doesn't jump when it appears.
        Column {
            visible: root.kind === "loading"
            width: parent.width
            spacing: Theme.space8
            topPadding: Theme.space4
            opacity: root.slow ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }
            Rectangle { width: parent.width; height: 12; radius: Theme.radiusSmall; color: Theme.surface2 }
            Rectangle { width: parent.width * 0.7; height: 12; radius: Theme.radiusSmall; color: Theme.surface2 }
            Text {
                text: "Looking at your tries"
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size14
            }
        }
    }
}
