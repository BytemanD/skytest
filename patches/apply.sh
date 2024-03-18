TAGET=/usr/local/lib/python3.10/site-packages/
patch -d $TAGET -p1 < fix-server-create-with-bdmv2.diff
