import QtQuick
import QtQuick.Window
import Theme
import "../components"

// Make a lesson from a YouTube video: paste the link and press Make a lesson. While it is made, each stage
// shows live. A ready lesson says which shelf it went on and opens from here; a video that can't become a
// lesson says why and lets you try another. Drawn as an outline: it is a tool, quieter than the lessons.
Rectangle {
    id: root
    property var factory: ({})
    property var courses: []
    signal make(string url)
    signal openLesson(string lessonId)
    signal dismiss()                    // the learner is done with the result; the backend clears it

    // Put the cursor in the link field, ready to paste.
    function focusLink() {
        dismissed = key
        if (root.Window.window)
            root.Window.window.requestActivate()
        input.forceActiveFocus()
    }

    readonly property string key: (factory.state || "idle") + "|" + (factory.url || "") + "|" + (factory.lessonId || "")
    property string dismissed: ""       // a finished result you put away; it stays away until the next one
    readonly property string showing: !factory.state || factory.state === "idle" || dismissed === key
                                      ? "idle" : factory.state
    property string problem: ""

    // The new lesson and the course it landed in.
    readonly property var landed: {
        for (const course of courses)
            for (const lesson of course.lessons || [])
                if (lesson.id === factory.lessonId)
                    return {"title": lesson.title, "course": course.title}
        return null
    }

    function send() {
        const url = input.text.trim()
        if (url === "")
            return
        if (!/^(https?:\/\/)?((www|m)\.)?(youtube\.com|youtu\.be)\//i.test(url)) {
            problem = "That link isn't from YouTube. Copy it from the video's page."
            return
        }
        problem = ""
        input.text = ""
        root.make(url)
    }

    readonly property real pad: Theme.space24
    implicitHeight: words.implicitHeight + 2 * pad
    radius: Theme.radiusLarge
    color: Theme.clear
    border.width: 2
    border.color: Theme.border

    Column {
        id: words
        x: root.pad
        y: root.pad
        width: parent.width - 2 * root.pad
        spacing: Theme.space16

        Column {
            width: parent.width
            spacing: Theme.space4

            Row {
                width: parent.width
                spacing: Theme.space8
                Glyph {
                    visible: root.showing === "ready"
                    anchors.verticalCenter: parent.verticalCenter
                    name: "tick"
                    colour: Theme.right
                    size: 22
                    stroke: 3
                }
                Text {
                    width: parent.width - (root.showing === "ready" ? 22 + Theme.space8 : 0)
                    text: root.showing === "running" ? "Making your lesson"
                          : root.showing === "not_ready" ? "Lesson not ready"
                          : root.showing === "ready" ? "Your lesson is ready"
                          : "Make a lesson from a video"
                    wrapMode: Text.Wrap
                    color: Theme.text
                    font.family: Theme.fontHeading
                    font.weight: Font.Bold
                    font.pixelSize: Theme.size20
                }
            }

            Text {
                visible: root.showing === "running" || root.showing === "not_ready"
                width: parent.width
                text: root.factory.url || ""
                elide: Text.ElideMiddle
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size14
            }

            Text {
                visible: root.showing === "ready"
                width: parent.width
                text: root.landed ? root.landed.title + " is on your " + root.landed.course + " shelf."
                                  : "It is on your shelf."
                wrapMode: Text.Wrap
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size16
            }
        }

        StageList {
            visible: root.showing === "running" || root.showing === "not_ready"
            width: parent.width
            gap: Theme.space12
            // Once it has stopped, only the stages that ran: what worked, and where it stopped.
            stages: (root.factory.stages || []).filter(st => root.showing === "running" || st.state !== "waiting")
        }

        Text {
            visible: root.showing === "not_ready" && text !== ""
            width: parent.width
            text: root.factory.reason || ""
            wrapMode: Text.Wrap
            color: Theme.text
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
        }

        // The link field.
        Rectangle {
            visible: root.showing === "idle"
            width: parent.width
            height: 48
            radius: Theme.radiusMedium
            color: Theme.surface1
            border.width: 2
            border.color: input.activeFocus ? Theme.text : Theme.border

            TextInput {
                id: input
                x: Theme.space16
                width: parent.width - 2 * Theme.space16
                height: parent.height
                verticalAlignment: TextInput.AlignVCenter
                clip: true
                maximumLength: 500
                selectByMouse: true
                color: Theme.text
                selectionColor: Theme.border
                selectedTextColor: Theme.text
                font.family: Theme.fontBody
                font.pixelSize: Theme.size16
                Accessible.role: Accessible.EditableText
                Accessible.name: "YouTube link"
                onAccepted: root.send()
                onTextChanged: root.problem = ""
            }
            Text {
                visible: input.text === "" && !input.activeFocus
                x: Theme.space16
                width: parent.width - 2 * Theme.space16
                anchors.verticalCenter: parent.verticalCenter
                text: "Paste a YouTube link"
                elide: Text.ElideRight
                color: Theme.muted
                font.family: Theme.fontBody
                font.pixelSize: Theme.size16
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.IBeamCursor
                onPressed: (mouse) => {
                    input.forceActiveFocus()
                    mouse.accepted = false
                }
            }
        }

        Text {
            visible: root.showing === "idle" && root.problem !== ""
            width: parent.width
            text: root.problem
            wrapMode: Text.Wrap
            color: Theme.notYet
            font.family: Theme.fontBody
            font.pixelSize: Theme.size14
        }

        ChunkyButton {
            visible: root.showing === "idle"
            width: parent.width
            kind: "quiet"
            text: "Make a lesson"
            enabled: input.text.trim() !== ""
            onClicked: root.send()
        }

        ChunkyButton {
            visible: root.showing === "not_ready"
            width: parent.width
            kind: "quiet"
            text: "Try another video"
            onClicked: { root.focusLink(); root.dismiss() }
        }

        Row {
            visible: root.showing === "ready"
            width: parent.width
            spacing: Theme.space8
            ChunkyButton {
                width: parent.width - another.width - Theme.space8
                kind: "right"
                text: "Open the lesson"
                onClicked: { root.openLesson(root.factory.lessonId); root.dismiss() }
            }
            ChunkyButton {
                id: another
                kind: "quiet"
                text: "Make another"
                onClicked: { root.focusLink(); root.dismiss() }
            }
        }
    }
}
