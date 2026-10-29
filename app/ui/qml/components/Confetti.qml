import QtQuick
import Theme

// The one big celebration's burst: coral, gold and mint pieces thrown up from (originX, originY), falling
// and fading out within 500 ms. It never takes a click, so nothing waits for it. Only position, scale and
// opacity move: each piece tumbles by squeezing its width.
Item {
    id: root
    property real originX: width / 2
    property real originY: height / 3
    property int count: 36
    property real t: 0
    property var pieces: []

    function fire() {
        const colours = [Theme.accent, Theme.reward, Theme.right]
        const made = []
        for (let i = 0; i < count; i++) {
            const angle = -Math.PI / 2 + (Math.random() - 0.5) * 2.2
            const speed = 220 + Math.random() * 220
            made.push({
                "colour": colours[i % colours.length],
                "round": i % 4 === 0,
                "w": i % 4 === 0 ? 8 : 6 + Math.round(Math.random() * 3),
                "h": i % 4 === 0 ? 8 : 10 + Math.round(Math.random() * 4),
                "vx": Math.cos(angle) * speed,
                "vy": Math.sin(angle) * speed,
                "fall": 380 + Math.random() * 160,
                "spin": (Math.random() < 0.5 ? -1 : 1) * (8 + Math.random() * 10)
            })
        }
        pieces = made
        burst.restart()
    }

    enabled: false
    visible: burst.running

    NumberAnimation {
        id: burst
        target: root
        property: "t"
        from: 0
        to: 1
        duration: 500
        easing.type: Easing.Linear
    }

    Repeater {
        model: root.pieces
        delegate: Rectangle {
            required property var modelData
            width: modelData.w
            height: modelData.h
            radius: modelData.round ? width / 2 : 0
            color: modelData.colour
            x: root.originX + modelData.vx * root.t - width / 2
            y: root.originY + modelData.vy * root.t + modelData.fall * root.t * root.t - height / 2
            opacity: 1 - Math.pow(root.t, 3)
            transform: Scale {
                origin.x: width / 2
                xScale: Math.cos(modelData.spin * root.t)
            }
        }
    }
}
