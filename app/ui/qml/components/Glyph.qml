import QtQuick
import QtQuick.Shapes
import Theme

// A small line drawing: tick, cross, lock, sound or muted. Drawn on a 24 unit grid, scaled to `size`.
Item {
    id: root
    property string name: "tick"
    property color colour: Theme.text
    property real size: 20
    property real stroke: 2.6

    readonly property var paths: ({
        "tick": "M5 12.5 L10 17.5 L19 7",
        "cross": "M7 7 L17 17 M17 7 L7 17",
        "lock": "M6.5 11 L17.5 11 L17.5 19.5 L6.5 19.5 Z M9 11 L9 8.5 C9 4.5 15 4.5 15 8.5 L15 11",
        "sound": "M4 9.5 L7.5 9.5 L12 5.5 L12 18.5 L7.5 14.5 L4 14.5 Z M15.5 9 C17 10.5 17 13.5 15.5 15 M18 6.5 C21 9.5 21 14.5 18 17.5",
        "muted": "M4 9.5 L7.5 9.5 L12 5.5 L12 18.5 L7.5 14.5 L4 14.5 Z M16 9.5 L21 14.5 M21 9.5 L16 14.5"
    })

    implicitWidth: size
    implicitHeight: size

    Shape {
        width: 24
        height: 24
        scale: root.size / 24
        transformOrigin: Item.TopLeft
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: root.colour
            strokeWidth: root.stroke * 24 / root.size
            fillColor: Theme.clear
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.paths[root.name] || "" }
        }
    }
}
