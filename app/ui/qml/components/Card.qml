import QtQuick
import Theme

// A plain surface that groups things. Level 1 sits on the base, level 2 sits on level 1 with a smaller
// corner, so nested corners stay even. No shadow: the surface step is the depth. Children stack in a
// column inside the padding; give them `width: parent.width`.
Rectangle {
    id: root
    property int level: 1
    property int padding: Theme.space16
    property alias spacing: column.spacing
    default property alias content: column.data

    implicitWidth: 320
    implicitHeight: column.implicitHeight + 2 * padding
    radius: level === 2 ? Theme.radiusMedium : Theme.radiusLarge
    color: level === 2 ? Theme.surface2 : Theme.surface1

    Column {
        id: column
        x: root.padding
        y: root.padding
        width: root.width - 2 * root.padding
        spacing: Theme.space8
    }
}
