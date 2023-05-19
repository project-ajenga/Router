from setuptools import find_namespace_packages, setup

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

packages = find_namespace_packages(include=('ajenga.router',
                                            'ajenga.router.*'))

setup(
    name='ajenga-router',
    version='1.3.0',
    url='https://github.com/project-ajenga/ajenga',
    license='MIT License',
    author='Hieuzest',
    author_email='girkirin@hotmail.com',
    description='An asynchronous QQ bot framework.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=packages,
    package_data={
        '': ['*.pyi'],
    },
    install_requires=[],
    extras_require={},
    python_requires='>=3.7',
    platforms='any',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Framework :: Robot Framework',
        'Framework :: Robot Framework :: Library',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
    ],
)
