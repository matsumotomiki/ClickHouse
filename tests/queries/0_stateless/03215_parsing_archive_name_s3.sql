-- Tags: no-fasttest
-- Tag no-fasttest: Depends on AWS

SELECT _file, _path FROM s3(s3_conn, filename='::03215_archive.csv') ORDER BY (_file, _path);
SELECT _file, _path FROM s3(s3_conn, filename='test :: 03215_archive.csv') ORDER BY (_file, _path); -- { serverError STD_EXCEPTION }
SELECT _file, _path FROM s3(s3_conn, filename='test::03215_archive.csv') ORDER BY (_file, _path);
