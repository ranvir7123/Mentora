import QtQuick
import Theme
import "../components"

// The courses, each a card with its name run over in the course's own highlighter, a progress bar and who
// made the videos. The course you are in stands large on the left; the others stack beside it. A course
// that isn't ready says "Coming soon" and is drawn as an empty outline, never as made-up content.
Item {
    id: root
    property var courses: []
    property string featuredId: ""
    signal open(string courseId)

    readonly property var featured: courses.find(c => c.id === featuredId) || courses[0] || null
    readonly property var others: courses.filter(c => !featured || c.id !== featured.id)
    readonly property bool sideBySide: width >= 560 && others.length > 0
    readonly property real gap: Theme.space16

    // Ring the course a new lesson has just landed in, for a moment.
    function flash(courseId) {
        if (featured && featured.id === courseId)
            big.flash()
        for (let i = 0; i < cards.count; ++i) {
            const card = cards.itemAt(i)
            if (card && card.course.id === courseId)
                card.flash()
        }
    }

    implicitHeight: sideBySide ? big.height : big.height + (others.length ? gap + stack.implicitHeight : 0)

    component CourseCard: Item {
        id: card
        property var course: ({})
        property bool big: false
        signal clicked()

        readonly property bool ready: !!course.ready
        readonly property var lessons: course.lessons || []
        readonly property int done: lessons.filter(l => l.state === "done").length
        readonly property var credits: course.credits || []
        readonly property var next: lessons.find(l => l.state === "current") || null
        // What the foot shows, decided from the course: never from the parts' own `visible`, which turns
        // false with the foot's and would keep a hidden foot hidden for good.
        readonly property bool showsNext: big && ready && next !== null
        readonly property bool showsCredits: credits.length > 0
        readonly property real pad: big ? Theme.space24 : Theme.space16
        readonly property bool down: area.pressed && ready

        function flash() { glow.restart() }

        implicitHeight: words.implicitHeight + (foot.visible ? words.spacing + foot.implicitHeight : 0)
                        + 2 * pad + (ready ? Theme.edge : 0)
        activeFocusOnTab: ready
        Accessible.role: Accessible.Button
        Accessible.name: (course.title || "") + (ready ? "" : ", coming soon")
        Accessible.onPressAction: if (ready) card.clicked()
        Keys.onSpacePressed: if (ready) card.clicked()
        Keys.onReturnPressed: if (ready) card.clicked()

        // A ready course stands on a darker edge, like the buttons, because it opens.
        Rectangle {
            visible: card.ready
            y: Theme.edge
            width: parent.width
            height: parent.height - Theme.edge
            radius: Theme.radiusLarge
            color: Theme.border
        }

        Item {
            id: lifted
            y: card.down ? Theme.edge : 0
            width: parent.width
            height: parent.height - (card.ready ? Theme.edge : 0)
            Behavior on y { NumberAnimation { duration: Theme.durFast; easing.type: Easing.OutCubic } }

            Rectangle {
                anchors.fill: parent
                radius: Theme.radiusLarge
                color: card.ready ? Theme.surface1 : Theme.bg
                border.width: card.ready ? (card.activeFocus ? 2 : 0) : 2
                border.color: card.ready ? Theme.text : Theme.border
            }

            Column {
                id: words
                x: card.pad
                y: card.pad
                width: parent.width - x - card.pad
                spacing: card.big ? Theme.space12 : Theme.space8

                // A ready course's name is marked in its colour; one still to come is plain grey words.
                Mark {
                    visible: card.ready
                    width: Math.min(implicitWidth, parent.width)
                    text: card.course.title || ""
                    colour: Theme.course(card.course.colour)
                    family: Theme.fontDisplay
                    pixelSize: card.big ? Theme.size24 : Theme.size20
                    spacing: Theme.tightDisplay
                }
                Text {
                    visible: !card.ready
                    width: parent.width
                    text: card.course.title || ""
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    color: Theme.muted
                    font.family: Theme.fontDisplay
                    font.weight: Font.ExtraBold
                    font.letterSpacing: Theme.tightDisplay
                    font.pixelSize: Theme.size20
                }
                ProgressBar {
                    visible: (!card.big || !mini.fits) && card.ready && card.lessons.length > 0
                    width: parent.width
                    value: card.lessons.length > 0 ? card.done / card.lessons.length : 0
                    label: card.done + " of " + card.lessons.length
                    segments: card.lessons.length
                }
                // The big card shows the course's lessons in miniature instead of a bar, while they fit.
                Row {
                    visible: card.big && mini.fits && card.ready && card.lessons.length > 0
                    width: parent.width
                    spacing: Theme.space12
                    MiniPath {
                        id: mini
                        width: Math.min(implicitWidth, parent.width - tally.width - parent.spacing)
                        lessons: card.lessons
                    }
                    Text {
                        id: tally
                        anchors.verticalCenter: mini.verticalCenter
                        text: card.done + " of " + card.lessons.length
                        color: Theme.muted
                        font.family: Theme.fontBody
                        font.weight: Font.Bold
                        font.pixelSize: Theme.size14
                    }
                }
                Text {
                    visible: !card.ready || card.lessons.length === 0
                    width: parent.width
                    text: card.ready ? "No lessons yet" : "Coming soon"
                    color: Theme.muted
                    font.family: Theme.fontBody
                    font.weight: Font.Bold
                    font.pixelSize: Theme.size14
                }
            }

            // At the foot of the card: on the big card, the lesson up next; then who made the videos, like an
            // author's name on a cover.
            Column {
                id: foot
                visible: card.showsNext || card.showsCredits
                x: words.x
                y: Math.max(words.y + words.height + words.spacing, parent.height - card.pad - height)
                width: words.width
                spacing: Theme.space16

                Column {
                    id: upNext
                    visible: card.showsNext
                    width: parent.width
                    spacing: Theme.space4
                    Text {
                        text: "Up next"
                        color: Theme.muted
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.size12
                    }
                    Text {
                        width: parent.width
                        text: card.next ? card.next.title : ""
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        color: Theme.text
                        font.family: Theme.fontBody
                        font.weight: Font.Bold
                        font.pixelSize: Theme.size16
                    }
                }

                Text {
                    id: madeBy
                    visible: card.showsCredits
                    width: parent.width
                    text: {
                        const names = card.credits
                        const list = names.length < 2 ? names.join("")
                                   : names.slice(0, -1).join(", ") + " and " + names[names.length - 1]
                        return "From videos by " + list
                    }
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    color: Theme.muted
                    font.family: Theme.fontBody
                    font.pixelSize: Theme.size14
                }
            }
        }

        // A short green ring round a course a new lesson has just landed in.
        Rectangle {
            id: ring
            objectName: "highlight"
            anchors.fill: parent
            anchors.margins: -Theme.space8
            radius: Theme.radiusLarge + Theme.space8
            color: Theme.clear
            border.width: 3
            border.color: Theme.right
            opacity: 0
            visible: opacity > 0
        }
        SequentialAnimation {
            id: glow
            NumberAnimation { target: ring; property: "opacity"; to: 1; duration: Theme.durFast; easing.type: Easing.OutCubic }
            PauseAnimation { duration: 900 }
            NumberAnimation { target: ring; property: "opacity"; to: 0; duration: 400; easing.type: Easing.OutCubic }
        }

        MouseArea {
            id: area
            anchors.fill: parent
            enabled: card.ready
            cursorShape: Qt.PointingHandCursor
            onClicked: card.clicked()
        }
    }

    CourseCard {
        id: big
        visible: root.featured !== null
        course: root.featured || ({})
        big: true
        width: root.sideBySide ? root.width - root.gap - stack.width : root.width
        height: root.sideBySide ? Math.max(implicitHeight, stack.implicitHeight) : implicitHeight
        onClicked: root.open(course.id)
    }

    // The smaller cards: a column beside the big one, or under it in a narrow window.
    Column {
        id: stack
        x: root.sideBySide ? root.width - width : 0
        y: root.sideBySide ? 0 : big.height + root.gap
        width: root.sideBySide ? Math.round((root.width - root.gap) * 0.42) : root.width
        spacing: root.gap
        Repeater {
            id: cards
            model: root.others
            delegate: CourseCard {
                required property var modelData
                course: modelData
                width: stack.width
                onClicked: root.open(modelData.id)
            }
        }
    }
}
