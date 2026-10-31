import QtQuick
import QtQuick.Window
import Theme
import "components"
import "home"

// The app's main window. At the top, hello, your streak and today's points. Below, the lesson you are
// part way through (or your first one), your courses, your common mistakes, tips from Meta's AI and making
// a lesson from a video. Opening a course shows its path instead, until you go back to all courses.
Window {
    id: root
    required property var bridge
    readonly property var home: bridge.home
    property string courseId: ""        // the course whose path is open; empty shows everything
    onCourseIdChanged: scroller.contentY = 0

    readonly property var courses: home.courses || []
    readonly property var openCourse: courses.find(c => c.id === courseId && c.ready) || null
    readonly property bool wide: width >= 1000
    readonly property real margin: wide ? Theme.space32 : Theme.space24
    readonly property real sideWidth: 352
    readonly property bool coachKeyMissing: home.meta === "no_key"        // the key of the AI that writes tips
    readonly property bool makerKeyMissing: home.makerKey === "no_key"    // Meta's, for making lessons
    readonly property bool claude: home.ai === "claude"     // MENTORA_AI=claude: Claude writes the tips

    // Read from `home` itself: inside onHomeChanged, `courses` may not have caught up yet.
    function courseOf(lessonId) {
        return (home.courses || []).find(c => (c.lessons || []).some(l => l.id === lessonId)) || null
    }

    // The lesson a first run starts with: the one up next in the first ready course that has lessons.
    readonly property var first: {
        for (const course of courses) {
            const lesson = course.ready ? (course.lessons || []).find(l => l.state === "current") : null
            if (lesson)
                return {"id": lesson.id, "title": lesson.title, "courseTitle": course.title}
        }
        return null
    }
    readonly property var resumeCourse: home.continueCard ? courseOf(home.continueCard.lessonId) : null

    width: 1120
    height: 720
    minimumWidth: 640
    minimumHeight: 480
    visible: true
    color: Theme.bg
    title: "Mentora"

    // Centred on the primary screen, and never bigger than what is free of its taskbar.
    Component.onCompleted: {
        const area = bridge.workArea
        width = Math.min(width, area.width - 2 * Theme.space24)
        height = Math.min(height, area.height - 2 * Theme.space24)
        x = area.x + (area.width - width) / 2
        y = area.y + (area.height - height) / 2
    }

    // A lesson that has just been made lands on its course's card with a short highlight.
    property string factoryWas: ""
    onHomeChanged: {
        const now = home.factory ? home.factory.state : ""
        if (now === "ready" && factoryWas !== "ready") {
            const course = courseOf(home.factory.lessonId)
            if (course)
                shelf.flash(course.id)
        }
        factoryWas = now
    }

    Header {
        id: header
        x: root.margin
        y: Theme.space24
        width: root.width - 2 * root.margin
        learner: root.home.learner || ({})
        muted: root.bridge.muted
        onToggleSound: root.bridge.setMuted(!root.bridge.muted)
    }

    Flickable {
        id: scroller
        y: header.y + header.height + Theme.space24
        width: root.width
        height: root.height - y
        contentWidth: width
        contentHeight: page.height + Theme.space24
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Item {
            id: page
            width: scroller.width
            height: root.openCourse ? path.y + path.implicitHeight
                                    : root.wide ? Math.max(main.height, side.height) : side.y + side.height

            Column {
                id: main
                visible: !root.openCourse
                x: root.margin
                width: root.wide ? root.width - 2 * root.margin - Theme.space32 - root.sideWidth
                                 : root.width - 2 * root.margin
                spacing: Theme.space32

                ContinueCard {
                    width: parent.width
                    card: root.home.continueCard || null
                    first: root.first
                    courseTitle: root.resumeCourse ? root.resumeCourse.title : ""
                    onContinueLesson: root.bridge.continueLesson()
                    onStart: (lessonId) => root.bridge.openLesson(lessonId)
                }

                Column {
                    width: parent.width
                    spacing: Theme.space16
                    Text {
                        text: "Your courses"
                        color: Theme.text
                        font.family: Theme.fontHeading
                        font.weight: Font.Bold
                        font.pixelSize: Theme.size20
                    }
                    CourseShelf {
                        id: shelf
                        width: parent.width
                        courses: root.courses
                        featuredId: root.resumeCourse ? root.resumeCourse.id : ""
                        onOpen: (id) => root.courseId = id
                    }
                }

                MistakesCard {
                    width: parent.width
                    mistakes: root.home.mistakes || []
                    onPractise: (lessonId, stepIndex) => root.bridge.practise(lessonId, stepIndex)
                }
            }

            Column {
                id: side
                visible: !root.openCourse
                x: root.wide ? main.x + main.width + Theme.space32 : root.margin
                y: root.wide ? 0 : main.height + Theme.space32
                width: root.wide ? root.sideWidth : main.width
                spacing: Theme.space24

                TipsCard {
                    visible: !root.coachKeyMissing
                    width: parent.width
                    tips: root.home.tips || ({})
                    ai: root.home.ai || "meta"
                }

                // A missing key: tips and the Ask box wait for the coach's AI's key, making lessons for Meta's.
                // When Meta coaches that is one key, so one card asks for it.
                KeyCard {
                    id: coachKey
                    visible: root.coachKeyMissing
                    width: parent.width
                    ai: root.claude ? "claude" : "meta"
                    need: root.makerKeyMissing && !root.claude ? "Lessons from videos and tips need it."
                                                               : "Tips and the Ask box need it."
                    onCopy: root.bridge.copyKeySetup(ai)
                }

                MakeLesson {
                    id: maker
                    visible: !root.makerKeyMissing
                    width: parent.width
                    factory: root.home.factory || ({})
                    courses: root.courses
                    onMake: (url) => root.bridge.makeLesson(url)
                    onOpenLesson: (lessonId) => root.bridge.openLesson(lessonId)
                    onDismiss: root.bridge.dismissFactory()
                }

                KeyCard {              // not when Meta coaches without its key: the card above asks for it
                    id: metaKey
                    visible: root.makerKeyMissing && !(root.coachKeyMissing && !root.claude)
                    width: parent.width
                    ai: "meta"
                    need: "Lessons from videos need it."
                    onCopy: root.bridge.copyKeySetup(ai)
                }
            }

            CoursePath {
                id: path
                visible: root.openCourse !== null
                x: root.margin
                width: root.width - 2 * root.margin
                course: root.openCourse || ({})
                onOpenLesson: (lessonId) => root.bridge.openLesson(lessonId)
                onBack: root.courseId = ""
                onMakeLesson: {        // to the maker, or to the card asking for the key it waits for
                    root.courseId = ""
                    const target = !root.makerKeyMissing ? maker : metaKey.visible ? metaKey : coachKey
                    maker.focusLink()
                    scroller.contentY = Math.max(0, Math.min(side.y + target.y,
                                                             scroller.contentHeight - scroller.height))
                }
            }
        }
    }
}
