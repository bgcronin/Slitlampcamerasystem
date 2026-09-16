from __future__ import annotations

import copy
import math

from PIL import Image
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsEllipseItem,
    QGraphicsRectItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QInputDialog,
    QColorDialog,
    QTabWidget,
    QLabel,
    QDialogButtonBox,
    QCheckBox,
)

from ..imaging import load_image, adjustments, render
from .common import pixmap, error


class AnnotationItem(QGraphicsItemGroup):
    def __init__(self, data: dict, width: int, height: int):
        super().__init__()
        self.data = copy.deepcopy(data)
        self.canvas_width, self.canvas_height = width, height
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setHandlesChildEvents(True)
        points = [QPointF(x * width, y * height) for x, y in data["points"]]
        colour = QColor(data.get("color", "#facc15"))
        pen = QPen(colour, max(1, data.get("width", 0.003) * width))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        kind = data["kind"]
        if kind == "text":
            child = QGraphicsTextItem(data.get("text", ""))
            font = QFont("Arial")
            font.setPixelSize(max(8, int(data.get("size", 0.025) * width)))
            child.setFont(font)
            child.setDefaultTextColor(colour)
            child.setPos(points[0])
            self.addToGroup(child)
        elif len(points) >= 2:
            bounds = QRectF(points[0], points[-1]).normalized()
            if kind == "ellipse":
                child = QGraphicsEllipseItem(bounds)
                child.setPen(pen)
                self.addToGroup(child)
            elif kind == "rectangle":
                child = QGraphicsRectItem(bounds)
                child.setPen(pen)
                self.addToGroup(child)
            else:
                path = QPainterPath(points[0])
                for p in points[1:]:
                    path.lineTo(p)
                child = QGraphicsPathItem(path)
                child.setPen(pen)
                self.addToGroup(child)
                if kind == "arrow":
                    a, b = points[0], points[-1]
                    angle = math.atan2(b.y() - a.y(), b.x() - a.x())
                    length = max(pen.widthF() * 5, width * 0.015)
                    tip1 = QPointF(
                        b.x() - length * math.cos(angle - 0.45), b.y() - length * math.sin(angle - 0.45)
                    )
                    tip2 = QPointF(
                        b.x() - length * math.cos(angle + 0.45), b.y() - length * math.sin(angle + 0.45)
                    )
                    head = QGraphicsPolygonItem(QPolygonF([b, tip1, tip2]))
                    head.setBrush(colour)
                    head.setPen(pen)
                    self.addToGroup(head)

    def serialise(self):
        data = copy.deepcopy(self.data)
        data["points"] = [
            [
                (x * self.canvas_width + self.pos().x()) / self.canvas_width,
                (y * self.canvas_height + self.pos().y()) / self.canvas_height,
            ]
            for x, y in data["points"]
        ]
        return data


class AnnotationCanvas(QGraphicsView):
    changed = Signal()
    crop_selected = Signal(object)

    def __init__(self, image: Image.Image, annotations: list, parent=None):
        super().__init__(parent)
        self.scene_object = QGraphicsScene(self)
        self.setScene(self.scene_object)
        self.image = image
        self.background = self.scene().addPixmap(pixmap(image))
        self.background.setZValue(-10)
        self.scene().setSceneRect(0, 0, image.width, image.height)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#070d16"))
        self.tool = "select"
        self.colour = "#facc15"
        self.stroke = 0.003
        self.text_size = 0.025
        self.drawing = []
        self.rubber = None
        self.items_list = []
        self.set_annotations(annotations)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def set_annotations(self, annotations):
        for item in self.items_list:
            self.scene().removeItem(item)
        self.items_list = []
        for data in annotations:
            item = AnnotationItem(data, self.image.width, self.image.height)
            self.scene().addItem(item)
            self.items_list.append(item)

    def annotations(self):
        return [item.serialise() for item in self.items_list]

    def set_image(self, image):
        self.background.setPixmap(pixmap(image))

    def point(self, event):
        p = self.mapToScene(event.position().toPoint())
        return [max(0, min(1, p.x() / self.image.width)), max(0, min(1, p.y() / self.image.height))]

    def mousePressEvent(self, event):
        if self.tool in ("select", "pan") or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.drawing = [self.point(event)]
        if self.tool == "text":
            text, ok = QInputDialog.getText(self, "Text annotation", "Label")
            if ok and text:
                self.add_annotation(
                    {
                        "kind": "text",
                        "points": self.drawing,
                        "text": text,
                        "color": self.colour,
                        "size": self.text_size,
                    }
                )
            self.drawing = []

    def mouseMoveEvent(self, event):
        if not self.drawing:
            super().mouseMoveEvent(event)
            return
        p = self.point(event)
        if self.tool == "freehand":
            self.drawing.append(p)
        else:
            self.drawing = [self.drawing[0], p]
        if self.rubber:
            self.scene().removeItem(self.rubber)
        data = {
            "kind": "rectangle" if self.tool == "crop" else self.tool,
            "points": self.drawing,
            "color": self.colour,
            "width": self.stroke,
        }
        self.rubber = AnnotationItem(data, self.image.width, self.image.height)
        self.scene().addItem(self.rubber)

    def mouseReleaseEvent(self, event):
        if self.drawing:
            if self.rubber:
                self.scene().removeItem(self.rubber)
                self.rubber = None
            points = self.drawing
            self.drawing = []
            if len(points) >= 2:
                if self.tool == "crop":
                    a, b = points[0], points[-1]
                    if abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
                        self.crop_selected.emit(
                            [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
                        )
                else:
                    self.add_annotation(
                        {"kind": self.tool, "points": points, "color": self.colour, "width": self.stroke}
                    )
        else:
            super().mouseReleaseEvent(event)
            if self.tool == "select":
                self.changed.emit()

    def add_annotation(self, data):
        item = AnnotationItem(data, self.image.width, self.image.height)
        self.scene().addItem(item)
        self.items_list.append(item)
        self.changed.emit()

    def remove_selected(self):
        for item in list(self.items_list):
            if item.isSelected():
                self.items_list.remove(item)
                self.scene().removeItem(item)
        self.changed.emit()

    def resize_selected(self, factor):
        for item in list(self.items_list):
            if not item.isSelected():
                continue
            data = item.serialise()
            pts = data["points"]
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            data["points"] = [[cx + (x - cx) * factor, cy + (y - cy) * factor] for x, y in pts]
            if data["kind"] == "text":
                data["size"] = data.get("size", 0.025) * factor
            self.scene().removeItem(item)
            self.items_list.remove(item)
            replacement = AnnotationItem(data, self.image.width, self.image.height)
            self.scene().addItem(replacement)
            self.items_list.append(replacement)
            replacement.setSelected(True)
        self.changed.emit()

    def wheelEvent(self, event):
        self.scale(
            1.15 if event.angleDelta().y() > 0 else 1 / 1.15, 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        )


class EditorDialog(QDialog):
    def __init__(self, catalog, mid, parent=None):
        super().__init__(parent)
        self.catalog, self.mid = catalog, mid
        self.item = catalog.media(mid)
        self.path = catalog.path(self.item["path"])
        self.original = load_image(self.path)
        self.edits = copy.deepcopy(self.item["edits"])
        self.history, self.future = [], []
        self.loading = False
        self.setWindowTitle("Edit & annotate · original file is preserved")
        self.resize(1150, 800)
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.tools = QComboBox()
        for label, value in [
            ("Select / move", "select"),
            ("Pan", "pan"),
            ("Arrow", "arrow"),
            ("Ellipse / circle", "ellipse"),
            ("Rectangle", "rectangle"),
            ("Freehand", "freehand"),
            ("Text", "text"),
            ("Crop", "crop"),
        ]:
            self.tools.addItem(label, value)
        toolbar.addWidget(self.tools)
        self.canvas = AnnotationCanvas(adjustments(self.original, self.edits), self.item["annotations"])
        self.tools.currentIndexChanged.connect(self.change_tool)
        for label, action in [
            ("Colour", self.choose_colour),
            ("Delete annotation", self.canvas.remove_selected),
            ("Smaller", lambda: self.canvas.resize_selected(0.9)),
            ("Larger", lambda: self.canvas.resize_selected(1.1)),
            ("Undo", self.undo),
            ("Redo", self.redo),
            (
                "Fit",
                lambda: self.canvas.fitInView(self.canvas.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio),
            ),
        ]:
            button = QPushButton(label)
            button.clicked.connect(action)
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        stylebar = QHBoxLayout()
        stylebar.addWidget(QLabel("Line thickness"))
        stroke = QDoubleSpinBox()
        stroke.setRange(0.1, 2)
        stroke.setValue(0.3)
        stroke.setSuffix("%")
        stroke.valueChanged.connect(lambda v: setattr(self.canvas, "stroke", v / 100))
        stylebar.addWidget(stroke)
        stylebar.addWidget(QLabel("Text size"))
        textsize = QSpinBox()
        textsize.setRange(1, 15)
        textsize.setValue(3)
        textsize.setSuffix("%")
        textsize.valueChanged.connect(lambda v: setattr(self.canvas, "text_size", v / 100))
        stylebar.addWidget(textsize)
        visible = QCheckBox("Show annotations")
        visible.setChecked(True)
        visible.toggled.connect(lambda value: [i.setVisible(value) for i in self.canvas.items_list])
        stylebar.addWidget(visible)
        stylebar.addStretch()
        layout.addLayout(stylebar)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.canvas, "Annotate")
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(400, 300)
        self.tabs.addTab(self.preview, "Output preview")
        self.compare = QLabel()
        self.compare.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.compare.setPixmap(
            pixmap(self.original).scaled(
                950, 540, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self.tabs.addTab(self.compare, "Original")
        self.tabs.currentChanged.connect(lambda index: self.update_preview() if index == 1 else None)
        layout.addWidget(self.tabs, 1)
        controls = QHBoxLayout()
        self.controls = {}
        for key, label, lo, hi, default in [
            ("brightness", "Brightness", 0.1, 3, 1),
            ("contrast", "Contrast", 0.1, 3, 1),
            ("warmth", "White balance", -1, 1, 0),
            ("sharpness", "Sharpen", 0, 2, 0),
            ("straighten", "Straighten °", -15, 15, 0),
        ]:
            column = QVBoxLayout()
            column.addWidget(QLabel(label))
            control = QDoubleSpinBox()
            control.setRange(lo, hi)
            control.setSingleStep(0.1 if key != "straighten" else 0.5)
            control.setValue(self.edits.get(key, default))
            control.valueChanged.connect(lambda v, k=key: self.set_edit(k, v))
            self.controls[key] = control
            column.addWidget(control)
            controls.addLayout(column)
        rotate = QPushButton("Rotate 90°")
        rotate.clicked.connect(lambda: self.set_edit("rotation", (self.edits.get("rotation", 0) + 90) % 360))
        controls.addWidget(rotate)
        reset = QPushButton("Reset all")
        reset.clicked.connect(self.reset)
        controls.addWidget(reset)
        layout.addLayout(controls)
        hint = QLabel(
            "Crop and rotation appear in Output preview. Annotations stay attached to the same image details."
        )
        hint.setObjectName("muted")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.canvas.changed.connect(self.remember)
        self.canvas.crop_selected.connect(lambda crop: self.set_edit("crop", crop))
        self.remember()

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.fitInView(self.canvas.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def change_tool(self):
        self.canvas.tool = self.tools.currentData()
        self.canvas.setDragMode(
            QGraphicsView.DragMode.ScrollHandDrag
            if self.canvas.tool == "pan"
            else QGraphicsView.DragMode.RubberBandDrag
            if self.canvas.tool == "select"
            else QGraphicsView.DragMode.NoDrag
        )

    def choose_colour(self):
        colour = QColorDialog.getColor(QColor(self.canvas.colour), self)
        if colour.isValid():
            self.canvas.colour = colour.name()

    def remember(self):
        if self.loading:
            return
        state = (copy.deepcopy(self.edits), self.canvas.annotations())
        if not self.history or self.history[-1] != state:
            self.history.append(state)
            self.history = self.history[-60:]
            self.future.clear()

    def restore_state(self, state):
        self.loading = True
        self.edits = copy.deepcopy(state[0])
        self.canvas.set_annotations(state[1])
        for key, control in self.controls.items():
            control.setValue(self.edits.get(key, 1 if key in ("brightness", "contrast") else 0))
        self.canvas.set_image(adjustments(self.original, self.edits))
        self.loading = False
        self.update_preview()

    def undo(self):
        if len(self.history) > 1:
            self.future.append(self.history.pop())
            self.restore_state(self.history[-1])

    def redo(self):
        if self.future:
            state = self.future.pop()
            self.history.append(state)
            self.restore_state(state)

    def set_edit(self, key, value):
        if self.loading:
            return
        self.edits[key] = value
        self.canvas.set_image(adjustments(self.original, self.edits))
        self.remember()
        if self.tabs.currentIndex() == 1:
            self.update_preview()

    def reset(self):
        self.restore_state(({}, []))
        self.remember()

    def update_preview(self):
        image = render(self.path, self.edits, self.canvas.annotations())
        self.preview.setPixmap(
            pixmap(image).scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def save(self):
        try:
            self.catalog.update_media(self.mid, edits=self.edits, annotations=self.canvas.annotations())
            self.accept()
        except Exception as exc:
            error(self, exc)
