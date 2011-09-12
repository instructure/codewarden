function readableDate(timestamp) {
  var date = new Date(timestamp);
  var hour = date.getHours();
  var am = hour < 12;
  hour = (hour - 1) % 12 + 1;
  var minutes = date.getMinutes();
  if(minutes < 10) { minutes = "0" + minutes; }
  return (date.getMonth() + 1) + '/' + date.getDate() + ' ' + hour + ':' +
      minutes + (am ? 'am' : 'pm');
}

$(document).ready(function() {
  var $announcement_row = $("#announcement").first();
  var $announcement = $announcement_row.find(".announcement").first();
  var $timestamp = $announcement_row.find(".timestamp").first();

  var addAnnouncement = function(a, is_new) {
    $announcement.html(a.announcement);
    $timestamp.html(readableDate(a.created_at * 1000));
    if(is_new) { $announcement_row.effect("highlight", {}, 6000); }
  };

  var last_timestamp = 0;
  var getAnnouncements = function() {
    setTimeout(getAnnouncements, 5000);
    $.getJSON("/announcements.json", {since: last_timestamp},
        function(announcements) {
      if(announcements.length == 0) return;
      for(var i = announcements.length; i > 0; --i) {
        addAnnouncement(announcements[i-1], last_timestamp != 0);
      }
      last_timestamp = announcements[0].created_at;
    });
  };
  getAnnouncements();
});
