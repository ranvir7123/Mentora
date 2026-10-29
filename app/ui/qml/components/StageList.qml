import QtQuick
import QtQuick.Shapes
import Theme

// The lesson maker's live stages, top to bottom, each with a mark (waiting, working, done or failed),
// its name in plain words and a detail line. A line joins the marks; it turns mint once a stage is done.
Column {
    id: root
    property var stages: []

    readonly property var names: ({
        "download": "Getting the video",
        "read": "Reading it",
        "write": "Writing the steps",
        "prove": "Proving every check in Excel",
        "test": "Meta's agent trying it",
        "publish": "Putting it on your shelf"
    })
    readonly property real mark: 24
    property real gap: Theme.space24             // the room under each stage; the home screen packs them tighter

    Accessible.role: Accessible.List

    Repeater {
        model: root.stages
        delegate: Item {
            id: row
            required property var modelData
            required property int index
            readonly property bool last: index === root.stages.length - 1
            readonly property string stage: modelData.state

            width: root.width
            height: Math.max(root.mark, words.implicitHeight) + (last ? 0 : root.gap)
            Accessible.role: Accessible.ListItem
            Accessible.name: words.name + ", " + stage + (modelData.detail ? ", " + modelData.detail : "")

            Rectangle {
                visible: !row.last
                x: root.mark / 2 - 1
                y: root.mark + Theme.space4
                width: 2
                height: row.height - root.mark - Theme.space8
                radius: 1
                color: row.stage === "done" ? Theme.right : Theme.border
            }

            // Waiting: an empty ring.
            Rectangle {
                visible: row.stage === "waiting"
                width: root.mark
                height: root.mark
                radius: width / 2
                color: Theme.clear
                border.width: 2
                border.color: Theme.border
            }

            // Working: a coral arc going round a quiet ring.
            Item {
                visible: row.stage === "running"
                width: root.mark
                height: root.mark
                Rectangle {
                    anchors.fill: parent
                    radius: width / 2
                    color: Theme.clear
                    border.width: 3
                    border.color: Theme.surface2
                }
                Shape {
                    id: spinner
                    anchors.fill: parent
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: Theme.accent
                        strokeWidth: 3
                        fillColor: Theme.clear
                        capStyle: ShapePath.RoundCap
                        PathAngleArc {
                            centerX: root.mark / 2
                            centerY: root.mark / 2
                            radiusX: root.mark / 2 - 1.5
                            radiusY: root.mark / 2 - 1.5
                            startAngle: -90
                            sweepAngle: 100
                        }
                    }
                    RotationAnimator on rotation {
                        running: row.stage === "running" && row.visible
                        from: 0
                        to: 360
                        duration: 800
                        loops: Animation.Infinite
                    }
                }
            }

            // Done and failed: a filled circle with a tick or a cross.
            Rectangle {
                visible: row.stage === "done" || row.stage === "failed"
                width: root.mark
                height: root.mark
                radius: width / 2
                color: row.stage === "done" ? Theme.right : Theme.notYet
                Glyph {
                    anchors.centerIn: parent
                    name: row.stage === "done" ? "tick" : "cross"
                    colour: Theme.onColour
                    size: 18
                    stroke: 3
                }
            }

            Column {
                id: words
                readonly property string name: root.names[row.modelData.name] || row.modelData.name
                x: root.mark + Theme.space12
                width: parent.width - x
                Text {
                    width: parent.width
                    text: words.name
                    wrapMode: Text.Wrap
                    color: row.stage === "waiting" ? Theme.muted : Theme.text
                    font.family: Theme.fontBody
                    font.weight: Font.Bold
                    font.pixelSize: Theme.size16
                }
                Text {
                    visible: text !== ""
                    width: parent.width
                    text: row.modelData.detail || ""
                    wrapMode: Text.Wrap
                    color: row.stage === "failed" ? Theme.notYet : Theme.muted
                    font.family: Theme.fontBody
                    font.pixelSize: Theme.size14
                }
            }
        }
    }
}
