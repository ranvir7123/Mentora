import QtQuick
import QtQuick.Shapes
import Theme
import "../components"
import "../mascot"

// One course opened: its name and who made the videos, then its lessons as square keys on a path that winds
// gently up and down (back and forth along the rows when there are many). Done lessons are ticked, the
// one you are on glows with the mascot sitting on it, later ones are locked. A course with no lessons
// yet says so and offers to make one.
Item {
    id: root
    property var course: ({})
    signal openLesson(string lessonId)
    signal back()
    signal makeLesson()

    readonly property var lessons: course.lessons || []
    readonly property int done: lessons.filter(l => l.state === "done").length
    readonly property int current: lessons.findIndex(l => l.state === "current")

    // The path's shape: up to `perRow` circles a row, `step` apart, each a little higher or lower than
    // the last (0, 1, 2, 1 times `rise`) so the line between them winds.
    readonly property real node: 136
    readonly property real circle: 72
    readonly property int perRow: Math.max(1, Math.floor(width / 168))
    readonly property int across: Math.max(1, Math.min(lessons.length, perRow))
    readonly property real step: Math.min(200, width / across)
    readonly property real rise: 36
    readonly property real headroom: 48                 // for the mascot on the first row
    readonly property real rowHeight: 140 + 2 * rise + Theme.space48
    readonly property var wave: [0, 1, 2, 1]

    function centre(i) {
        const row = Math.floor(i / perRow)
        const col = i % perRow
        const along = row % 2 === 0 ? col : perRow - 1 - col
        const left = (width - step * across) / 2
        return Qt.point(left + step * (along + 0.5), headroom + circle / 2 + row * rowHeight + rise * wave[i % 4])
    }

    // An SVG path through the circles' middles from lesson `from` to lesson `to`: S-curves along a row,
    // a U-turn between rows.
    function line(from, to) {
        if (to <= from)
            return ""
        let p = centre(from)
        let d = "M " + p.x + " " + p.y
        for (let i = from + 1; i <= to; ++i) {
            const q = centre(i)
            if (Math.floor(i / perRow) === Math.floor((i - 1) / perRow)) {
                const mid = (q.x - p.x) / 2
                d += " C " + (p.x + mid) + " " + p.y + " " + (q.x - mid) + " " + q.y + " " + q.x + " " + q.y
            } else {
                const out = (Math.floor(i / perRow) % 2 === 1 ? 1 : -1) * step * 0.6
                d += " C " + (p.x + out) + " " + p.y + " " + (q.x + out) + " " + q.y + " " + q.x + " " + q.y
            }
            p = q
        }
        return d
    }

    implicitHeight: top.height + Theme.space24 + (lessons.length > 0 ? path.height : empty.implicitHeight)

    Column {
        id: top
        width: parent.width
        spacing: Theme.space24

        ChunkyButton {
            kind: "quiet"
            compact: true
            text: "All courses"
            onClicked: root.back()
        }

        Item {
            width: parent.width
            height: heading.height
            Column {
                id: heading
                width: parent.width
                spacing: Theme.space12
                // The course's name, run over in its own highlighter, as on its card.
                Mark {
                    width: Math.min(implicitWidth, parent.width)
                    text: root.course.title || ""
                    colour: Theme.course(root.course.colour)
                    family: Theme.fontDisplay
                    pixelSize: Theme.size32
                    spacing: Theme.tightDisplay
                }
                Text {
                    visible: (root.course.credits || []).length > 0
                    width: parent.width
                    text: {
                        const names = root.course.credits || []
                        const list = names.length < 2 ? names.join("")
                                   : names.slice(0, -1).join(", ") + " and " + names[names.length - 1]
                        return "From videos by " + list
                    }
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    color: Theme.muted
                    font.family: Theme.fontBody
                    font.pixelSize: Theme.size16
                }
                ProgressBar {
                    visible: root.lessons.length > 0
                    width: Math.min(parent.width, 360)
                    value: root.lessons.length > 0 ? root.done / root.lessons.length : 0
                    label: root.done + " of " + root.lessons.length
                    segments: root.lessons.length
                }
            }
        }
    }

    Item {
        id: path
        visible: root.lessons.length > 0
        y: top.height + Theme.space24
        width: parent.width
        height: root.headroom + Math.ceil(root.lessons.length / root.perRow) * root.rowHeight - Theme.space48

        // The line between the keys: yellow up to the lesson you are on, quiet after it.
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.surface2
                strokeWidth: 10
                fillColor: Theme.clear
                capStyle: ShapePath.RoundCap
                PathSvg { path: root.line(Math.max(0, root.current < 0 ? root.lessons.length - 1 : root.current),
                                          root.lessons.length - 1) }
            }
            ShapePath {
                strokeColor: Theme.accent
                strokeWidth: 10
                fillColor: Theme.clear
                capStyle: ShapePath.RoundCap
                PathSvg { path: root.line(0, root.current < 0 ? root.lessons.length - 1 : root.current) }
            }
        }

        Repeater {
            id: nodes
            model: root.lessons
            delegate: PathNode {
                required property var modelData
                required property int index
                readonly property point middle: root.centre(index)
                x: middle.x - width / 2
                y: middle.y - circle / 2
                width: root.node
                title: modelData.title
                badge: modelData.badge || ""
                number: index + 1
                state: modelData.state
                onClicked: root.openLesson(modelData.id)
            }
        }

        Mascot {
            visible: root.current >= 0
            size: 44
            readonly property point on: root.centre(Math.max(0, root.current))
            x: on.x - size / 2
            y: on.y - root.circle / 2 - size + 10       // sitting on the top of the circle
            z: 1
        }
    }

    // No lessons in this course yet.
    Column {
        id: empty
        visible: root.lessons.length === 0
        y: top.height + Theme.space48
        width: parent.width
        spacing: Theme.space16

        Item {
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.circle
            height: root.circle + 44 - 10
            Rectangle {
                y: 44 - 10
                width: root.circle
                height: root.circle
                radius: Theme.radiusLarge
                color: Theme.clear
                border.width: 3
                border.color: Theme.border
            }
            Mascot {
                anchors.horizontalCenter: parent.horizontalCenter
                size: 44
            }
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "No lessons here yet"
            wrapMode: Text.Wrap
            color: Theme.text
            font.family: Theme.fontHeading
            font.weight: Font.ExtraBold
            font.pixelSize: Theme.size24
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "Make the first one from a YouTube video."
            wrapMode: Text.Wrap
            color: Theme.muted
            font.family: Theme.fontBody
            font.pixelSize: Theme.size16
        }
        Item { width: 1; height: Theme.space8 }
        ChunkyButton {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Make a lesson"
            onClicked: root.makeLesson()
        }
    }
}
