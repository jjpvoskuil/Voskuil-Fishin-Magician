-- fm-lures photo bucket: approved anglers can add/read/remove photos; outsiders and signed-out visitors can't.
\set ON_ERROR_STOP off
select set_config('request.jwt.claims', '{"email":"akvoskuil94@gmail.com"}', false);
set role authenticated;
insert into storage.objects (bucket_id, name) values ('fm-lures', 'lures/x.jpg');
select count(*) = 1 as "member can add + read a photo" from storage.objects where bucket_id = 'fm-lures';
reset role;
select set_config('request.jwt.claims', '{"email":"stranger@example.com"}', false);
set role authenticated;
select count(*) = 0 as "outsider sees no photos" from storage.objects;
insert into storage.objects (bucket_id, name) values ('fm-lures', 'lures/evil.jpg');
reset role;
select count(*) = 1 as "outsider's upload was refused" from storage.objects where bucket_id = 'fm-lures';
set role anon;
select count(*) = 0 as "signed-out sees no photos" from storage.objects;
reset role;
select set_config('request.jwt.claims', '{"email":"akvoskuil94@gmail.com"}', false);
set role authenticated;
delete from storage.objects where name = 'lures/x.jpg';
reset role;
select count(*) = 0 as "member can remove a photo" from storage.objects where bucket_id = 'fm-lures';
