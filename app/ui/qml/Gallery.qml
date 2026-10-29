import QtQuick
import QtQuick.Window
import Theme
import "components"

// Every building block in every variant, for the screenshot check. Not shown to learners.
Window {
    id: win
    property var bridge
    width: 1352
    height: 1040
    visible: true
    color: Theme.bg
    title: "Building blocks"

    component Label: Text {
        color: Theme.muted
        font.family: Theme.fontBody
        font.weight: Font.Bold
        font.pixelSize: Theme.size14
    }

    Sfx { id: sfx }

    Row {
        x: Theme.space48
        y: Theme.space48
        spacing: Theme.space48

        // Buttons, the progress bar and hints: the panel's width.
        Column {
            width: 360
            spacing: Theme.space16

            Label { text: "Buttons" }
            Flow {
                width: parent.width
                spacing: Theme.space12
                ChunkyButton { width: 174; text: "Show me" }
                ChunkyButton { width: 174; text: "Show me"; held: true }
                ChunkyButton { width: 174; text: "Hint"; kind: "quiet" }
                ChunkyButton { width: 174; text: "Next step"; kind: "right" }
                ChunkyButton { width: 174; text: "Continue"; enabled: false }
                ChunkyButton { width: 174; text: "Make a lesson from this long video link"; kind: "quiet" }
            }
            Row {
                spacing: Theme.space12
                ChunkyButton { text: "Play click"; kind: "quiet"; compact: true; onClicked: sfx.play("click") }
                ChunkyButton { text: "Play right"; kind: "quiet"; compact: true; onClicked: sfx.play("right") }
                ChunkyButton { text: "Play hop"; kind: "quiet"; compact: true; onClicked: sfx.play("hop") }
            }
            Row {
                spacing: Theme.space12
                ChunkyButton { text: "Play not yet"; kind: "quiet"; compact: true; onClicked: sfx.play("not_yet") }
                ChunkyButton { text: "Play complete"; kind: "quiet"; compact: true; onClicked: sfx.play("complete") }
            }
            Row {
                spacing: Theme.space12
                IconButton { glyph: "cross"; label: "Close the lesson" }
                IconButton { glyph: "sound"; label: "Turn sound off" }
                IconButton { glyph: "muted"; label: "Turn sound on"; held: true }
            }

            Label { text: "Progress" }
            ProgressBar { width: parent.width; value: 0; label: "1 of 9" }
            ProgressBar { width: parent.width; value: 3 / 9; label: "4 of 9" }
            ProgressBar { width: parent.width; value: 1; label: "9 of 9" }
            ProgressBar { width: parent.width; value: 0.6 }

            Label { text: "Hints" }
            HintList {
                width: parent.width
                hints: ["Click B8, below the amounts.", "Type =SUM( then select B2 to B6."]
                hintsLeft: 1
            }
            HintList {
                width: parent.width
                hints: ["Click B8, below the amounts.", "Type =SUM( then select B2 to B6.",
                        "Type =SUM(B2:B6) and press Enter. If Excel shows the formula as words, the cell is set to text: change it to General first."]
                hintsLeft: 0
            }
        }

        // Banners, as they rise over the bottom of the panel.
        Column {
            width: 360
            spacing: Theme.space16

            Label { text: "Banners" }
            Banner { width: parent.width; kind: "right"; turn: 0 }
            Banner { width: parent.width; kind: "right"; turn: 2; text: "Your total adds up all six amounts."; actionText: "Next step" }
            Banner { width: parent.width; kind: "not_yet"; text: "Not yet: your total skips B6. Include Fun too." }
            Banner { width: parent.width; kind: "changed"; text: "Step 2 came undone when B8 changed."; actionText: "Fix step 2" }
            Banner { width: parent.width; kind: "app_closed"; text: "Excel was closed. Your progress is saved."; actionText: "Reopen Excel" }
            Banner { width: parent.width; kind: "error"; text: "Meta's AI didn't answer. Check your internet, then ask again."; actionText: "Ask again" }
        }

        // Rewards, cards, the course path and the lesson maker.
        Column {
            width: 440
            spacing: Theme.space16

            Label { text: "Streak and today's points" }
            Row {
                spacing: Theme.space32
                StreakFlame { days: 0 }
                StreakFlame { days: 4 }
                StreakFlame { days: 128 }
                DailyRing { done: 0; goal: 50 }
                DailyRing { done: 30; goal: 50 }
                DailyRing { done: 50; goal: 50 }
            }

            Label { text: "Cards" }
            Row {
                spacing: Theme.space16
                Card {
                    width: 212
                    Text { width: parent.width; text: "Level one"; color: Theme.text; font.family: Theme.fontHeading; font.weight: Font.DemiBold; font.pixelSize: Theme.size20 }
                    Text { width: parent.width; text: "Sits on the base."; wrapMode: Text.Wrap; color: Theme.muted; font.family: Theme.fontBody; font.pixelSize: Theme.size14 }
                    Card {
                        level: 2
                        width: parent.width
                        Text { width: parent.width; text: "Level two sits on level one."; wrapMode: Text.Wrap; color: Theme.text; font.family: Theme.fontBody; font.pixelSize: Theme.size14 }
                    }
                }
                Card {
                    width: 212
                    level: 2
                    Text { width: parent.width; text: "Level two"; color: Theme.text; font.family: Theme.fontHeading; font.weight: Font.DemiBold; font.pixelSize: Theme.size20 }
                    Text { width: parent.width; text: "For a card inside a card, or a hint."; wrapMode: Text.Wrap; color: Theme.muted; font.family: Theme.fontBody; font.pixelSize: Theme.size14 }
                }
            }

            Label { text: "Course path" }
            Row {
                spacing: Theme.space16
                PathNode { state: "done"; number: 1; title: "Grade sheet"; badge: "proven and tested" }
                PathNode { state: "current"; number: 2; title: "Monthly budget"; badge: "proven and tested" }
                PathNode { state: "locked"; number: 3; title: "Track your monthly spending with a budget that adds itself up"; badge: "proven" }
            }

            Label { text: "Making a lesson" }
            Row {
                spacing: Theme.space24
                StageList {
                    width: 208
                    stages: [
                        { "name": "download", "state": "done", "detail": "" },
                        { "name": "read", "state": "done", "detail": "" },
                        { "name": "write", "state": "running", "detail": "Writing step 5 of 9" },
                        { "name": "prove", "state": "waiting", "detail": "" },
                        { "name": "test", "state": "waiting", "detail": "" },
                        { "name": "publish", "state": "waiting", "detail": "" }
                    ]
                }
                StageList {
                    width: 208
                    stages: [
                        { "name": "download", "state": "done", "detail": "" },
                        { "name": "read", "state": "done", "detail": "" },
                        { "name": "write", "state": "done", "detail": "" },
                        { "name": "prove", "state": "failed", "detail": "Steps 6 and 7 could not be proven in Excel" },
                        { "name": "test", "state": "waiting", "detail": "" },
                        { "name": "publish", "state": "waiting", "detail": "" }
                    ]
                }
            }
        }
    }
}
