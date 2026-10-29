import QtQuick
import Theme
import "../components"

// The step you are on: one short instruction, why it matters in a quieter line, a calm note when an
// earlier step came undone, then the help for it (Show me, Hint, the clip) and the hints asked for so far.
Card {
    id: root
    property var step: null
    property var changed: []            // earlier steps that came undone, counted from 0
    property string appName: ""
    property bool clipOpen: false
    property bool muted: false
    property bool canGetVideo: false    // the clip's source video may be opened in the browser
    signal showMe()
    signal hint()
    signal clip()
    signal getVideo()

    readonly property var clipInfo: step && step.clip ? step.clip : ({ "state": "none", "file": "", "start": 0,
                                                                         "end": 0, "videoUrl": "" })
    readonly property string changedLine: {
        const n = changed.map(i => i + 1)
        if (n.length === 0)
            return ""
        const where = appName !== "" ? " in " + appName + "." : "."
        if (n.length === 1)
            return "Step " + n[0] + " changed. Fix it" + where
        return "Steps " + n.slice(0, -1).join(", ") + " and " + n[n.length - 1] + " changed. Fix them" + where
    }

    spacing: Theme.space16
    Accessible.role: Accessible.Grouping
    Accessible.name: step ? step.instruction : ""

    Column {
        width: parent.width
        spacing: Theme.space4

        Text {
            width: parent.width
            text: root.step ? root.step.instruction : ""
            wrapMode: Text.Wrap
            color: Theme.text
            font.family: Theme.fontBody
            font.weight: Font.Bold
            font.pixelSize: Theme.size20
        }

        Text {
            visible: text !== ""
            width: parent.width
            text: root.step ? root.step.why : ""
            wrapMode: Text.Wrap
            color: Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size14
        }
    }

    Rectangle {
        visible: root.changedLine !== ""
        width: parent.width
        height: changedWords.implicitHeight + 2 * Theme.space12
        radius: Theme.radiusMedium
        color: Theme.surface2
        Accessible.role: Accessible.StaticText
        Accessible.name: changedWords.text

        Text {
            id: changedWords
            x: Theme.space12
            y: Theme.space12
            width: parent.width - 2 * Theme.space12
            text: root.changedLine
            wrapMode: Text.Wrap
            color: Theme.text
            font.family: Theme.fontBody
            font.weight: Font.Bold
            font.pixelSize: Theme.size14
        }
    }

    HelpRow {
        width: parent.width
        hasClip: root.clipInfo.state !== "none"
        clipOpen: root.clipOpen
        hintsLeft: root.step ? root.step.hintsLeft : 0
        onShowMe: root.showMe()
        onHint: root.hint()
        onClip: root.clip()
    }

    ClipPlayer {
        id: player
        visible: root.clipOpen && root.clipInfo.state !== "none"
        width: parent.width
        clip: root.clipInfo
        open: visible
        muted: root.muted
        canGetVideo: root.canGetVideo
        onGetVideo: root.getVideo()
    }

    HintList {
        width: parent.width
        hints: root.step ? root.step.hints : []
        hintsLeft: root.step ? root.step.hintsLeft : 0
        onMore: root.hint()
    }
}
