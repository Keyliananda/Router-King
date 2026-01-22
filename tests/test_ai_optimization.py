import unittest
from unittest.mock import patch

from RouterKing.ai.context import SelectionContext, SelectionItem
import RouterKing.ai.optimization as optimization


class FakePoint:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class FakeSplineCurve:
    TypeId = "Part::BSplineCurve"

    def __init__(self, pole_count):
        self._poles = [FakePoint() for _ in range(pole_count)]

    def getPoles(self):
        return list(self._poles)


class FakeBSplineCurve:
    TypeId = "Part::BSplineCurve"

    def __init__(self):
        self._poles = []

    def approximate(self, points, **_kwargs):
        count = max(2, min(8, max(2, len(points) // 8)))
        self._poles = [FakePoint() for _ in range(count)]

    def getPoles(self):
        return list(self._poles)

    def toShape(self):
        return FakeEdge(self)


class FakeEdge:
    def __init__(self, curve):
        self.Curve = curve

    def discretize(self, Number=None, Deflection=None):
        count = Number or 5
        return [FakePoint(float(i), 0.0, 0.0) for i in range(int(count))]


class FakeShape:
    def __init__(self, edges, faces=None):
        self.Edges = list(edges)
        self.Faces = list(faces or [])


class FakeViewObject:
    def __init__(self):
        self.LineColor = None
        self.LineWidth = None


class FakeDocObject:
    def __init__(self, name):
        self.Name = name
        self.Label = ""
        self.Shape = None
        self.ViewObject = FakeViewObject()


class FakeDocument:
    def __init__(self):
        self._objects = {}
        self._transactions = []

    def addObject(self, _type_name, name):
        obj = FakeDocObject(name)
        self._objects[name] = obj
        return obj

    def getObject(self, name):
        return self._objects.get(name)

    def removeObject(self, name):
        self._objects.pop(name, None)

    def openTransaction(self, name):
        self._transactions.append(("open", name))

    def commitTransaction(self):
        self._transactions.append(("commit", None))

    def abortTransaction(self):
        self._transactions.append(("abort", None))

    def recompute(self):
        self._transactions.append(("recompute", None))


class FakeApp:
    def __init__(self, doc=None):
        self.ActiveDocument = doc


class FakePart:
    BSplineCurve = FakeBSplineCurve

    @staticmethod
    def Compound(edges):
        return {"edges": list(edges)}


class TestAiOptimization(unittest.TestCase):
    def test_optimize_selection_no_selection(self):
        context = SelectionContext(warnings=["No selection found."])
        result = optimization.optimize_selection(context=context, create_preview=False)
        self.assertEqual(result.summary, "No selection.")
        self.assertTrue(result.issues)

    def test_optimize_selection_unavailable_without_part(self):
        curve = FakeSplineCurve(20)
        shape = FakeShape([FakeEdge(curve)])
        context = SelectionContext(
            items=[SelectionItem(obj=type("Obj", (), {"Shape": shape})(), label="Test", type_id="Part")]
        )
        with patch.object(optimization, "App", None), patch.object(optimization, "Part", None):
            result = optimization.optimize_selection(context=context, create_preview=False)
        self.assertEqual(result.summary, "Optimization unavailable.")
        self.assertTrue(result.issues)

    def test_optimize_selection_reduces_spline(self):
        curve = FakeSplineCurve(20)
        shape = FakeShape([FakeEdge(curve)])
        context = SelectionContext(
            items=[SelectionItem(obj=type("Obj", (), {"Shape": shape})(), label="Test", type_id="Part")]
        )
        with patch.object(optimization, "App", FakeApp()), patch.object(optimization, "Part", FakePart):
            result = optimization.optimize_selection(context=context, create_preview=False)
        self.assertEqual(result.stats["optimized_edges"], 1)
        self.assertEqual(len(result.optimized_targets), 1)
        self.assertIn("Optimized 1 spline edge", result.summary)

    def test_optimize_selection_creates_preview(self):
        curve = FakeSplineCurve(20)
        shape = FakeShape([FakeEdge(curve)])
        context = SelectionContext(
            items=[SelectionItem(obj=type("Obj", (), {"Shape": shape})(), label="Test", type_id="Part")]
        )
        doc = FakeDocument()
        with patch.object(optimization, "App", FakeApp(doc)), patch.object(optimization, "Part", FakePart):
            result = optimization.optimize_selection(context=context, create_preview=True)
        self.assertEqual(len(result.preview_objects), 1)
        preview = result.preview_objects[0]
        self.assertEqual(preview.Label, "Test (Spline Preview)")

    def test_create_optimized_object(self):
        doc = FakeDocument()
        shape = {"edges": []}
        optimized = optimization.create_optimized_object(doc, "Sample", shape)
        self.assertIsNotNone(optimized)
        self.assertEqual(optimized.Label, "Sample (Spline Optimized)")
        self.assertEqual(optimized.ViewObject.LineColor, (0.1, 0.4, 0.9))


if __name__ == "__main__":
    unittest.main()
