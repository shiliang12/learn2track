for d in "$@";
do
  mkdir -p $d/tractometer/tracks
  mv $d/*.tck $d/tractometer/tracks/
  ~/env/miccai2016_tractometer/bin/python ~/research/src/tractometer/scripts/ismrm_compute_submissions_attributes.py $d/tractometer/tracks/ $d/tractometer/attributes.json orientation;
  ~/env/miccai2016_tractometer/bin/python ~/research/src/tractometer/scripts/ismrm_compute_submissions_attributes.py $d/tractometer/tracks/ $d/tractometer/attributes.json count;
done