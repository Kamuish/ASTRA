import numpy as np


if __name__ == "__main__":
    print("COMPILING CYTHON")
    import Cython.Compiler.Options
    from Cython.Build import cythonize
    from setuptools import Extension, setup

    Cython.Compiler.Options.annotate = True

    targets = {
        "inverter": "inverter.pyx",
        "partial_derivative": "partial_derivative.pyx",
        "second_derivative": "second_derivative.pyx",
    }

    ext_modules = [
        Extension(
            key,
            [value],
            extra_compile_args=["-fopenmp"],
            extra_link_args=["-fopenmp"],
            include_dirs=[np.get_include()],
        )
        for key, value in targets.items()
    ]
    setup(ext_modules=cythonize(ext_modules, compiler_directives={"language_level": "3"}, annotate=True))
