import QtQuick
import QtQuick.Shapes
import Theme

// Today's points against the daily goal: a gold ring that fills, with today's points in the middle.
// A full ring shows a tick instead.
Item {
    id: root
    property int done: 0
    property int goal: 50
    property real size: 48
    property real thickness: 6

    readonly property real share: goal > 0 ? Math.max(0, Math.min(1, done / goal)) : 0
    readonly property real radius: (size - thickness) / 2

    implicitWidth: size
    implicitHeight: size
    Accessible.role: Accessible.ProgressBar
    Accessible.name: done + " of " + goal + " points today"

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: Theme.surface2
            strokeWidth: root.thickness
            fillColor: Theme.clear
            PathAngleArc {
                centerX: root.size / 2
                centerY: root.size / 2
                radiusX: root.radius
                radiusY: root.radius
                startAngle: 0
                sweepAngle: 360
            }
        }
        ShapePath {
            strokeColor: root.share > 0 ? Theme.reward : Theme.clear
            strokeWidth: root.thickness
            fillColor: Theme.clear
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: root.size / 2
                centerY: root.size / 2
                radiusX: root.radius
                radiusY: root.radius
                startAngle: -90
                sweepAngle: 360 * root.share
            }
        }
    }

    Text {
        visible: root.share < 1
        anchors.centerIn: parent
        text: root.done
        color: Theme.text
        font.family: Theme.fontBody
        font.weight: Font.ExtraBold
        font.pixelSize: Theme.size14
    }

    Glyph {
        visible: root.share >= 1
        anchors.centerIn: parent
        name: "tick"
        colour: Theme.reward
        size: root.size / 2
        stroke: 3
    }
}
