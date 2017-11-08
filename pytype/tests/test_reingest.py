"""Tests for reloading generated pyi."""

import unittest


from pytype import utils
from pytype.pytd import pytd
from pytype.tests import test_base


class ReingestTest(test_base.BaseTest):
  """Tests for reloading the pyi we generate."""

  def testContainer(self):
    ty = self.Infer("""
      class Container:
        def Add(self):
          pass
      class A(Container):
        pass
    """)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(ty))
      self.assertNoErrors("""
        # u.py
        from foo import A
        A().Add()
      """, pythonpath=[d.path])

  def testUnion(self):
    ty = self.Infer("""
      class Union(object):
        pass
      x = {"Union": Union}
    """)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(ty))
      self.assertNoErrors("""
        from foo import Union
      """, pythonpath=[d.path])

  def testIdentityDecorators(self):
    foo = self.Infer("""
      def decorate(f):
        return f
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      ty = self.Infer("""
        import foo
        @foo.decorate
        def f():
          return 3
        def g():
          return f()
      """, deep=True, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        foo = ...  # type: module
        def f() -> int
        def g() -> int
      """)

  @unittest.skip("Needs better handling of Union[Callable, f] in output.py.""")
  def testMaybeIdentityDecorators(self):
    foo = self.Infer("""
      def maybe_decorate(f):
        return f or (lambda *args: 42)
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      ty = self.Infer("""
        import foo
        @foo.maybe_decorate
        def f():
          return 3
        def g():
          return f()
      """, deep=True, pythonpath=[d.path])
      self.assertTypesMatchPytd(ty, """
        foo = ...  # type: module
        def f() -> int
        def g() -> int
      """)

  def testTypeParameterBound(self):
    foo = self.Infer("""
      from __future__ import google_type_annotations
      from typing import TypeVar
      T = TypeVar("T", bound=float)
      def f(x: T) -> T: return x
    """)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      _, errors = self.InferAndCheck("""\
        import foo
        foo.f("")
      """, pythonpath=[d.path])
      self.assertErrorLogIs(errors, [(2, "wrong-arg-types", r"float.*str")])

  def testNamedTuple(self):
    foo = self.Infer("""
      import collections
      X = collections.namedtuple("X", ["a", "b"])
    """)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      self.assertNoErrors("""
        import foo
        foo.X(0, 0)
        foo.X(a=0, b=0)
      """, pythonpath=[d.path])

  def testNewChain(self):
    foo = self.Infer("""
      class X(object):
        def __new__(cls, x):
          return super(X, cls).__new__(cls)
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      self.assertNoErrors("""
        import foo
        class Y(foo.X):
          def __new__(cls, x):
            return super(Y, cls).__new__(cls, x)
          def __init__(self, x):
            self.x = x
        Y("x").x
      """, pythonpath=[d.path])

  def testNamedTupleSubclass(self):
    foo = self.Infer("""
      import collections
      class X(collections.namedtuple("X", ["a"])):
        def __new__(cls, a, b):
          print b
          return super(X, cls).__new__(cls, a)
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      _, errors = self.InferAndCheck("""\
        import foo
        foo.X("hello", "world")
        foo.X(42)  # missing parameters
      """, pythonpath=[d.path])
      self.assertErrorLogIs(errors, [(3, "missing-parameter", "b.*__new__")])

  def testAlias(self):
    foo = self.Infer("""
      class _Foo(object):
        def __new__(cls, _):
          return super(_Foo, cls).__new__(cls)
      Foo = _Foo
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      self.assertNoErrors("""
        import foo
        foo.Foo("hello world")
      """, pythonpath=[d.path])

  def testDynamicAttributes(self):
    foo1 = self.Infer("""
      HAS_DYNAMIC_ATTRIBUTES = True
    """, deep=True)
    foo2 = self.Infer("""
      has_dynamic_attributes = True
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo1.pyi", pytd.Print(foo1))
      d.create_file("foo2.pyi", pytd.Print(foo2))
      d.create_file("bar.pyi", """\
        from foo1 import xyz
        from foo2 import zyx
      """)
      self.assertNoErrors("""
        import foo1
        import foo2
        import bar
        foo1.abc
        foo2.abc
        bar.xyz
        bar.zyx
      """, pythonpath=[d.path])

  def testDefaultArgumentType(self):
    foo = self.Infer("""
      from __future__ import google_type_annotations
      from typing import Any, Callable, TypeVar
      T = TypeVar("T")
      def f(x):
        return True
      def g(x: Callable[[T], Any]) -> T: ...
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      self.assertNoErrors("""
        import foo
        foo.g(foo.f).upper()
      """, pythonpath=[d.path])

  def testInstantiatePyiClass(self):
    foo = self.Infer("""
      import abc
      class Foo(object):
        __metaclass__ = abc.ABCMeta
        @abc.abstractmethod
        def foo(self):
          pass
      class Bar(Foo):
        def foo(self):
          pass
    """, deep=True)
    with utils.Tempdir() as d:
      d.create_file("foo.pyi", pytd.Print(foo))
      _, errors = self.InferAndCheck("""\
        import foo
        foo.Foo()
        foo.Bar()
      """, pythonpath=[d.path])
      self.assertErrorLogIs(errors, [(2, "not-instantiable", r"foo\.Foo.*foo")])


if __name__ == "__main__":
  test_base.main()
