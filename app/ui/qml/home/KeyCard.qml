import QtQuick
import Theme
import "../components"

// Asks for a missing key: `ai` names whose (Meta's or Claude's) and `need` says what waits for it; lessons
// themselves still work. The card copies the PowerShell line that saves the key, with a gap where the key goes.
Rectangle {
    id: root
    property string ai: "meta"          // or "claude"
    property string need: ""
    signal copy()

    height: column.implicitHeight + 2 * Theme.space24
    radius: Theme.radiusLarge
    color: Theme.clear
    border.width: 2
    border.color: Theme.border

    Column {
        id: column
        x: Theme.space24
        y: Theme.space24
        width: parent.width - 2 * Theme.space24
        spacing: Theme.space16

        Column {
            width: parent.width
            spacing: Theme.space4
            Text {
                width: parent.width
                text: root.ai === "claude" ? "Add your Claude key" : "Add your Meta key"
                wrapMode: Text.Wrap
                color: Theme.text
                font.family: Theme.fontHeading
                font.weight: Font.Bold
                font.pixelSize: Theme.size20
            }
            Text {
                width: parent.width
                text: root.need
                wrapMode: Text.Wrap
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size16
            }
        }

        ChunkyButton {
            id: copyLine
            property bool copied: false
            width: parent.width
            kind: "quiet"
            text: copied ? "Copied" : "Copy the setup line"
            onClicked: {
                root.copy()
                copied = true
                copiedFor.restart()
            }
            Timer { id: copiedFor; interval: 2000; onTriggered: copyLine.copied = false }
        }

        Text {
            width: parent.width
            text: "Paste it in PowerShell, put your key in it, and press Enter."
            wrapMode: Text.Wrap
            color: Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size14
        }
    }
}
