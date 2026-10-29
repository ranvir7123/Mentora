import QtQuick
import Theme
import "../components"

// Help for the step: Show me (the mascot flies to the target again), Hint, and Watch the clip when the step
// has one. Each button is as wide as its words need, and the spare room is shared out so the buttons fill
// the card. When all three don't fit on one line, Watch the clip takes a second line of its own. The clip
// button keeps one width whether it says Watch or Hide.
Item {
    id: root
    property bool hasClip: false
    property bool clipOpen: false
    property int hintsLeft: 0
    signal showMe()
    signal hint()
    signal clip()

    readonly property real pad: 2 * Theme.space16      // a button keeps 16 px either side of its words
    readonly property real showWidth: showWords.advanceWidth + pad
    readonly property real hintWidth: hintWords.advanceWidth + pad
    readonly property real clipWidth: Math.max(watchWords.advanceWidth, hideWords.advanceWidth) + pad
    readonly property bool oneLine: !hasClip
                                    || showWidth + hintWidth + clipWidth + 2 * Theme.space8 <= width
    readonly property real spare: oneLine && hasClip
                                  ? (width - showWidth - hintWidth - clipWidth - 2 * Theme.space8) / 3
                                  : (width - showWidth - hintWidth - Theme.space8) / 2

    implicitHeight: oneLine ? 40 : 2 * 40 + Theme.space8

    TextMetrics { id: showWords; font: show.labelFont; text: show.text }
    TextMetrics { id: hintWords; font: show.labelFont; text: hint.text }
    TextMetrics { id: watchWords; font: show.labelFont; text: "Watch the clip" }
    TextMetrics { id: hideWords; font: show.labelFont; text: "Hide the clip" }

    ChunkyButton {
        id: show
        readonly property font labelFont: Qt.font({ family: Theme.fontBody, weight: Font.ExtraBold,
                                                    pixelSize: Theme.size14 })
        width: Math.floor(root.showWidth + root.spare)
        kind: "quiet"
        compact: true
        text: "Show me"
        onClicked: root.showMe()
    }

    ChunkyButton {
        id: hint
        x: show.width + Theme.space8
        // The last button on its line takes the rounding left over, so the line ends on the card's edge.
        width: root.hasClip && root.oneLine ? Math.floor(root.hintWidth + root.spare) : root.width - x
        kind: "quiet"
        compact: true
        text: root.hintsLeft > 0 ? "Hint" : "No hints left"
        enabled: root.hintsLeft > 0
        onClicked: root.hint()
    }

    ChunkyButton {
        visible: root.hasClip
        x: root.oneLine ? hint.x + hint.width + Theme.space8 : 0
        y: root.oneLine ? 0 : 40 + Theme.space8
        width: root.width - x
        kind: "quiet"
        compact: true
        text: root.clipOpen ? "Hide the clip" : "Watch the clip"
        onClicked: root.clip()
    }
}
