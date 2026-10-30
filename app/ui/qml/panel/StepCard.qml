import QtQuick
import Theme
import "../components"

// The step you are on: one short instruction, why it matters in a quieter line, a note from the app (such
// as "save first"), a calm note when an earlier step came undone with a link that points at it, then the
// help for it (Show me, Hint, the clip) and the hints asked for so far.
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
    signal goTo(int index)              // point at an earlier step that came undone

    readonly property var clipInfo: step && step.clip ? step.clip : ({ "state": "none", "file": "", "start": 0,
                                                                         "end": 0, "videoUrl": "" })
    // The step on screen is left out: it is the one being done.
    readonly property var undone: changed.filter(i => !step || i !== step.index)
    readonly property string changedLine: {
        const n = undone.map(i => i + 1)
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
        visible: noteWords.text !== ""
        width: parent.width
        height: noteWords.implicitHeight + 2 * Theme.space12
        radius: Theme.radiusMedium
        color: Theme.surface2
        Accessible.role: Accessible.StaticText
        Accessible.name: noteWords.text

        Text {
            id: noteWords
            x: Theme.space12
            y: Theme.space12
            width: parent.width - 2 * Theme.space12
            text: root.step ? (root.step.note || "") : ""
            wrapMode: Text.Wrap
            color: Theme.text
            font.family: Theme.fontBody
            font.weight: Font.Bold
            font.pixelSize: Theme.size14
        }
    }

    Rectangle {
        visible: root.changedLine !== ""
        width: parent.width
        height: changedColumn.implicitHeight + 2 * Theme.space12
        radius: Theme.radiusMedium
        color: Theme.surface2
        Accessible.role: Accessible.Grouping
        Accessible.name: changedWords.text

        Column {
            id: changedColumn
            x: Theme.space12
            y: Theme.space12
            width: parent.width - 2 * Theme.space12
            spacing: Theme.space8

            Text {
                id: changedWords
                width: parent.width
                text: root.changedLine
                wrapMode: Text.Wrap
                color: Theme.text
                font.family: Theme.fontBody
                font.weight: Font.Bold
                font.pixelSize: Theme.size14
            }

            Text {
                id: where
                text: "Show me where"
                color: Theme.accent
                font.family: Theme.fontBody
                font.weight: Font.ExtraBold
                font.pixelSize: Theme.size14
                font.underline: whereArea.containsMouse || where.activeFocus
                activeFocusOnTab: true
                Accessible.role: Accessible.Link
                Accessible.name: text
                Accessible.onPressAction: root.goTo(root.undone[0])
                Keys.onSpacePressed: root.goTo(root.undone[0])
                Keys.onReturnPressed: root.goTo(root.undone[0])

                MouseArea {
                    id: whereArea
                    anchors.fill: parent
                    anchors.margins: -Theme.space8
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.goTo(root.undone[0])
                }
            }
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
