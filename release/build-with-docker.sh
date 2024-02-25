python -m pip install build
python -m build

cd release

cp ../dist/skytest-0.1.0-py3-none-any.whl ./
cp ../etc/skytest.template.toml ./

podman build -t skytest ./

rm -rf skytest.template.toml skytest-*.whl
