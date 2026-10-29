import QtQuick
import QtQuick.Shapes
import Theme

// Shows its children (a picture, a video) with rounded corners: four small corner pieces in the colour
// behind it are drawn over the children's corners. Unlike a mask effect this works in every renderer (the
// off-screen screenshots use the software one) and needs no extra layer. Give the children
// `anchors.fill: parent`, and set `behind` to the colour the item sits on.
Item {
    id: root
    property real radius: Theme.radiusMedium
    property color behind: Theme.surface1
    default property alias content: inner.data

    Item {
        id: inner
        anchors.fill: parent
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: root.behind
            strokeColor: "transparent"
            strokeWidth: 0

            PathMove { x: 0; y: 0 }
            PathLine { x: root.radius; y: 0 }
            PathArc { x: 0; y: root.radius; radiusX: root.radius; radiusY: root.radius; direction: PathArc.Counterclockwise }
            PathLine { x: 0; y: 0 }

            PathMove { x: root.width; y: 0 }
            PathLine { x: root.width; y: root.radius }
            PathArc { x: root.width - root.radius; y: 0; radiusX: root.radius; radiusY: root.radius; direction: PathArc.Counterclockwise }
            PathLine { x: root.width; y: 0 }

            PathMove { x: root.width; y: root.height }
            PathLine { x: root.width - root.radius; y: root.height }
            PathArc { x: root.width; y: root.height - root.radius; radiusX: root.radius; radiusY: root.radius; direction: PathArc.Counterclockwise }
            PathLine { x: root.width; y: root.height }

            PathMove { x: 0; y: root.height }
            PathLine { x: 0; y: root.height - root.radius }
            PathArc { x: root.radius; y: root.height; radiusX: root.radius; radiusY: root.radius; direction: PathArc.Counterclockwise }
            PathLine { x: 0; y: root.height }
        }
    }
}
