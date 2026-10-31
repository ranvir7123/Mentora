import QtQuick
import QtQuick.Window
import Theme
import "components"
import "mascot"
import "panel"

// The lesson panel, docked on the right while the real app fills the rest of the screen. Top to bottom:
// close, progress and sound; the goal (open on the first step, then one tap away); the step with its
// help, hints and clip; your question and its answer; the Ask box pinned to the bottom. Right and Not yet
// slide up over the bottom. The mascot rests on the first card's top-right corner and tells the bridge
// where, so the pointer's mascot can fly out from there and back. A finished lesson swaps the step for the
// one big celebration and the Ask box for Next lesson and Home.
//
// The panel never takes the keyboard from the app; only the Ask box asks for it while you type.
Window {
    id: root
    required property var bridge
    readonly property var lesson: bridge.lesson
    property bool clipOpen: false           // the step's clip is open (a demo state may open it)
    property bool goalOpen: true

    readonly property bool finished: !!lesson.complete
    readonly property bool appClosed: lesson.appState === "closed"
    readonly property var ask: lesson.ask || ({ "state": "idle", "question": "", "answer": "" })
    // The app the lesson runs in: as the backend names it, else by its course; empty when it isn't known.
    readonly property string appName: {
        if (lesson.appName)
            return lesson.appName
        const courses = bridge.home.courses || []
        for (const course of courses) {
            if ((course.lessons || []).some(l => l.id === lesson.id))
                return course.app === "excel" ? "Excel" : course.app === "vscode" ? "VS Code" : ""
        }
        return ""
    }

    width: 360
    height: bridge.workArea.height
    x: bridge.workArea.x + bridge.workArea.width - width
    y: bridge.workArea.y
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    visible: root.lesson.open
    color: Theme.bg
    title: "Mentora lesson"

    // A new step folds the goal away (it stays open on the first step) and closes the clip.
    property string seen: ""
    function newStep() {
        const now = lesson.id + "#" + lesson.stepIndex
        if (now === seen)
            return
        seen = now
        goalOpen = lesson.stepIndex === 0
        clipOpen = false
    }
    onLessonChanged: newStep()
    onFinishedChanged: if (finished) Qt.callLater(celebrate)
    onActiveChanged: if (!active) bridge.askFocused(false)
    Component.onCompleted: {
        newStep()
        if (finished)
            Qt.callLater(celebrate)
        built = true
    }

    function toggleClip() {
        clipOpen = !clipOpen
        if (clipOpen) {
            bridge.watchClip()
            reveal(step)
        }
    }

    // Scroll just enough to show the bottom of `item`, after the layout has caught up. Not while the panel is
    // being built: a lesson opens at its top, whatever it already shows.
    property bool built: false
    function reveal(item) {
        if (!built)
            return
        Qt.callLater(() => {
            if (!item.visible)
                return
            const top = item.mapToItem(scroller.contentItem, 0, 0).y
            const most = Math.max(0, scroller.contentHeight - scroller.height)
            const want = Math.min(most, Math.max(0, top + item.height + Theme.space16 - scroller.height), top)
            if (want > scroller.contentY) {
                scrollTo.to = want
                scrollTo.restart()
            }
        })
    }
    NumberAnimation {
        id: scrollTo
        target: scroller
        property: "contentY"
        duration: Theme.durNormal
        easing.type: Easing.OutCubic
    }

    function celebrate() {
        results.start()
        const c = perch.mapToItem(null, perch.size / 2, perch.size / 2)
        confetti.originX = c.x
        confetti.originY = c.y
        confetti.fire()
    }

    // Where the mascot rests, in screen coordinates. Kept inside the scrolling area, so a scrolled-away
    // card still gets a mascot back at its edge.
    function reportHome() {
        if (!visible)
            return
        const p = perch.mapToItem(null, 0, 0)
        const y = Math.max(scroller.y, Math.min(p.y, scroller.y + scroller.height - perch.size))
        bridge.mascotHome = Qt.rect(root.x + p.x, root.y + y, perch.size, perch.size)
    }
    Timer { id: homeLater; interval: 0; onTriggered: root.reportHome() }
    onXChanged: homeLater.restart()
    onYChanged: homeLater.restart()
    onHeightChanged: homeLater.restart()
    onVisibleChanged: homeLater.restart()

    // A right try: a short cheer and a hop.
    property bool cheering: false
    Timer { id: cheer; interval: 900; onTriggered: root.cheering = false }

    Connections {
        target: root.bridge
        function onCue(name, points) {
            sfx.play(name)
            if (name === "right") {
                if (points > 0) {           // a step passed again earns nothing, so nothing floats up
                    plusPoints.text = "+" + points
                    floating.restart()
                }
                root.cheering = true
                cheer.restart()
            }
        }
    }

    Sfx { id: sfx; muted: root.bridge.muted }

    TopBar {
        x: Theme.space16
        y: Theme.space16
        width: root.width - 2 * Theme.space16
        stepIndex: root.lesson.stepIndex
        stepCount: root.lesson.stepCount
        muted: root.bridge.muted
        onClose: root.bridge.closeLesson()
        onToggleSound: root.bridge.setMuted(!root.bridge.muted)
    }

    Flickable {
        id: scroller
        y: Theme.space16 + 40
        width: root.width
        height: bottom.y - y
        contentWidth: width
        // A banner taller than the Ask box covers the end of the cards; room is added so they scroll clear.
        contentHeight: middle.y + middle.height + Theme.space16 + Math.max(0, banner.reach - bottom.height)
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        onContentYChanged: homeLater.restart()

        Column {
            id: middle
            x: Theme.space16
            y: Theme.space24                 // room above the mascot for its hop
            width: root.width - 2 * Theme.space16
            spacing: Theme.space16

            // The lesson's name (or the folded goal) on the left; the mascot standing on the card below.
            Item {
                id: header
                width: parent.width
                // The mascot's curl (9) and body (48) reach down across the 16 px gap onto the card.
                height: Math.max(9 + perch.size - middle.spacing, lead.height)
                onHeightChanged: homeLater.restart()

                Item {
                    id: lead
                    anchors.bottom: parent.bottom
                    width: perch.x - Theme.space16
                    height: chip.visible ? chip.height : heading.height

                    GoalChip {
                        id: chip
                        visible: !root.goalOpen && !root.finished
                        anchors.bottom: parent.bottom
                        maxWidth: lead.width
                        width: implicitWidth
                        sentence: root.lesson.goal ? root.lesson.goal.sentence : ""
                        onOpen: root.goalOpen = true
                    }

                    Column {
                        id: heading
                        visible: !chip.visible
                        anchors.bottom: parent.bottom
                        width: parent.width
                        spacing: Theme.space4

                        Text {
                            width: parent.width
                            text: root.finished ? "Lesson done!" : root.lesson.title
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontHeading
                            font.weight: Font.Bold
                            font.pixelSize: root.finished ? Theme.size32 : Theme.size24
                            Accessible.role: Accessible.Heading
                        }
                        Text {
                            visible: root.finished
                            width: parent.width
                            text: root.lesson.title
                            wrapMode: Text.Wrap
                            color: Theme.muted
                            font.family: Theme.fontBody
                            font.weight: Font.Bold
                            font.pixelSize: Theme.size16
                        }
                    }
                }

                Mascot {
                    id: perch
                    x: parent.width - Theme.space16 - size       // over the card's inner edge
                    y: parent.height + middle.spacing - size     // standing on the card below
                    size: 48
                    state: root.finished || root.cheering ? "cheering"
                           : answer.thinking && answer.slow ? "thinking" : "resting"
                    opacity: root.bridge.mascotAway ? 0 : 1      // the pointer's mascot is out
                    z: 1
                }
            }

            GoalCard {
                visible: root.goalOpen && !root.finished
                width: parent.width
                goal: root.lesson.goal
                foldable: root.lesson.stepIndex > 0
                onFold: root.goalOpen = false
            }

            Card {
                visible: root.appClosed && !root.finished
                width: parent.width
                spacing: Theme.space12
                Accessible.role: Accessible.AlertMessage
                Accessible.name: closedHeading.text

                Text {
                    id: closedHeading
                    width: parent.width
                    text: root.lesson.closedReason || ((root.appName || "The app") + " was closed")
                    wrapMode: Text.Wrap
                    color: Theme.text
                    font.family: Theme.fontHeading
                    font.weight: Font.Bold
                    font.pixelSize: Theme.size24
                }
                Text {
                    width: parent.width
                    text: "Open it again to carry on with step "
                          + ((root.lesson.step ? root.lesson.step.index : root.lesson.stepIndex) + 1) + "."
                    wrapMode: Text.Wrap
                    color: Theme.muted
                    font.family: Theme.fontBody
                    font.pixelSize: Theme.size16
                }
                Item { width: 1; height: Theme.space4 }
                ChunkyButton {
                    width: parent.width
                    kind: "main"
                    text: root.appName ? "Reopen " + root.appName : "Reopen the app"
                    onClicked: root.bridge.reopenApp()
                }
            }

            StepCard {
                id: step
                visible: !!root.lesson.step && !root.appClosed && !root.finished
                width: parent.width
                step: root.lesson.step
                changed: root.lesson.changed || []
                appName: root.appName
                clipOpen: root.clipOpen
                muted: root.bridge.muted
                canGetVideo: root.bridge.isVideoLink(clipInfo.videoUrl)
                onShowMe: root.bridge.showMe()
                onHint: root.bridge.nextHint()
                onClip: root.toggleClip()
                onGetVideo: root.bridge.openVideo(clipInfo.videoUrl)
                onGoTo: (index) => root.bridge.goToStep(index)
                readonly property int hintCount: root.lesson.step ? root.lesson.step.hints.length : 0
                onHintCountChanged: if (hintCount > 0) root.reveal(step)
            }

            AnswerCard {
                id: answer
                visible: root.ask.state !== "idle" && root.ask.question !== "" && !root.finished
                width: parent.width
                ask: root.ask
                onVisibleChanged: if (visible) root.reveal(answer)
                onHeightChanged: if (visible) root.reveal(answer)
            }

            Complete {
                id: results
                visible: root.finished
                width: parent.width
                complete: root.lesson.complete || ({ "points": 0, "seconds": 0, "firstTry": 0, "steps": 0,
                                                     "streak": 0, "streakBefore": 0 })
            }
        }
    }

    // A thin bar on the right edge while there is more to scroll to.
    Rectangle {
        visible: scroller.contentHeight > scroller.height + 1
        x: root.width - Theme.space8
        y: scroller.y + scroller.visibleArea.yPosition * scroller.height
        width: Theme.space4
        height: scroller.visibleArea.heightRatio * scroller.height
        radius: Theme.radiusSmall
        color: Theme.border
    }

    // Pinned to the bottom: the Ask box, or what to do after the lesson.
    Item {
        id: bottom
        y: root.height - height
        width: root.width
        height: (root.finished ? after.height : askBox.height) + 2 * Theme.space16

        AskBox {
            id: askBox
            visible: !root.finished
            x: Theme.space16
            y: Theme.space16
            width: root.width - 2 * Theme.space16
            busy: root.ask.state === "thinking"
            onAsk: (question) => root.bridge.ask(question)
            onTyping: (on) => root.bridge.askFocused(on)
        }

        Column {
            id: after
            visible: root.finished
            x: Theme.space16
            y: Theme.space16
            width: root.width - 2 * Theme.space16
            spacing: Theme.space8

            ChunkyButton {
                width: parent.width
                kind: "main"
                text: "Next lesson"
                onClicked: root.bridge.nextLesson()
            }
            ChunkyButton {
                width: parent.width
                kind: "quiet"
                text: "Home"
                onClicked: root.bridge.goHome()
            }
        }
    }

    // Right and Not yet slide up over the bottom. Not yet can be put away to get back to the Ask box; it
    // comes back with the next wrong try, even the same mistake again (that may arrive as the sound alone).
    property var shownBanner: null          // kept while it slides away
    property string putAway: ""
    function bannerKey(b) { return b ? b.kind + "|" + b.stepIndex + "|" + b.text : "" }
    readonly property bool bannerUp: !!lesson.banner && !finished && bannerKey(lesson.banner) !== putAway
    onBannerUpChanged: if (bannerUp) shownBanner = lesson.banner
    Connections {
        target: root
        function onLessonChanged() {
            if (root.lesson.banner)
                root.shownBanner = root.lesson.banner
            if (root.bannerKey(root.lesson.banner) !== root.putAway)
                root.putAway = ""
        }
    }
    Connections {
        target: root.bridge
        function onCue(name) { if (name === "not_yet") root.putAway = "" }
    }

    MouseArea {                             // the banner is solid: a click on it never reaches the Ask box
        enabled: banner.shown
        anchors.fill: banner
    }

    Banner {
        id: banner
        y: root.height - height
        width: root.width
        height: Math.max(implicitHeight, bottom.height)
        kind: root.shownBanner ? root.shownBanner.kind : "right"
        text: root.shownBanner ? root.shownBanner.text : ""
        turn: root.shownBanner ? root.shownBanner.stepIndex : 0
        actionText: kind === "not_yet" ? "Try again" : kind === "changed" ? "Show me where" : ""
        shown: root.bannerUp
        enabled: shown
        Component.onCompleted: if (root.lesson.banner) root.shownBanner = root.lesson.banner
        onAction: {
            if (kind === "changed")
                root.bridge.goToStep(root.shownBanner.stepIndex)
            else
                root.putAway = root.bannerKey(root.shownBanner)
        }
    }

    // A press anywhere in the panel but the Ask box puts the keyboard back in the app, then goes on to
    // whatever was pressed. On top of everything, and it never keeps a press.
    MouseArea {
        anchors.fill: parent
        z: 1000
        onPressed: (mouse) => {
            if (!askBox.contains(mapToItem(askBox, mouse.x, mouse.y)))
                askBox.letGo()
            mouse.accepted = false
        }
    }

    // The points earned (+10) in gold, floating up from the right banner and fading, all within 400 ms. It
    // rides on the banner as it slides up, so it never shows over the Ask box ahead of it.
    Text {
        id: plusPoints
        x: root.width - Theme.space16 - width
        y: root.height - banner.reach + banner.headingCentre - height / 2
        opacity: 0
        text: ""
        color: Theme.reward
        font.family: Theme.fontBody
        font.weight: Font.ExtraBold
        font.pixelSize: Theme.size24
        transform: Translate { id: rise }
    }
    ParallelAnimation {
        id: floating
        NumberAnimation { target: rise; property: "y"; from: 0; to: -24; duration: 400; easing.type: Easing.OutCubic }
        SequentialAnimation {
            PropertyAction { target: plusPoints; property: "opacity"; value: 1 }
            PauseAnimation { duration: 150 }
            NumberAnimation { target: plusPoints; property: "opacity"; to: 0; duration: 250; easing.type: Easing.InQuad }
        }
    }

    Confetti {
        id: confetti
        anchors.fill: parent
    }
}
