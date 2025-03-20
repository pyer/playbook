#!/usr/bin/env perl
#
# Monitorix - A lightweight system monitoring tool.
#
# Copyright (C) 2005-2022 by Jordi Sanfeliu <jordi@fibranet.cat>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

use strict;
use warnings;
use File::Basename;
use FindBin qw($Bin);
use lib $Bin . "/lib", "/usr/lib/monitorix";

use Monitorix;
use CGI qw(:standard);
use Config::General;
use POSIX;
use RRDs;
use Encode;
use Fcntl qw(:flock);

my %config;
my %cgi;
my %colors;
my %tf;
my @version12;
my @version12_small;


sub page_header {
  my ($logo, $title, $twhen) = @_;

  print("  <body>\n");
#  print("    <img src=\"$logo\" border=\"0\">\n");
  print("    <h1>$title&nbsp;&nbsp;-&nbsp;&nbsp;last&nbsp;$twhen</h1>\n");
  print("    <img src=\"$logo\" border=\"0\">\n");
  print encode('utf-8', "    <h4 class='text-title-date'>" . strftime("%a %b %e %H:%M:%S %Z %Y", localtime) . "</h4>\n");
}

sub page_footer {
  print("  </body>\n");
  print("</html>\n");
}


sub graph_header {
  my ($title, $colspan) = @_;
  my @output;

  push(@output, "\n");
  push(@output, "<!-- graph table begins -->\n");
  push(@output, "  <table class='table-module' width='1' >\n");
  push(@output, "    <tr>\n");
  push(@output, "      <td class='td-title' colspan='$colspan'>\n");
  push(@output, "          <b>&nbsp;&nbsp;$title</b>\n");
  push(@output, "      </td>\n");
  push(@output, "    </tr>\n");
  return @output;
}

sub graph_footer {
  my @output;

  push(@output, "  </table>\n");
  push(@output, "<!-- graph table ends -->\n");
  return @output;
}


# MAIN
# ----------------------------------------------------------------------------
my $config_path = "/etc/monitorix/monitorix.conf";

# load main configuration file
my $conf = new Config::General(
  -ConfigFile  => $config_path,
);
%config = $conf->getall;

our $silent = '';
our $graph = param('graph');
our $when = param('when');
our $color = param('color');
our $val = '';

# this should disarm all XSS and Cookie Injection attempts
my $OK_CHARS='-a-zA-Z0-9_';  # a restrictive list of valid chars
$graph =~ s/[^$OK_CHARS]/_/go;  # only $OK_CHARS are allowed
$when =~ s/[^$OK_CHARS]/_/go;  # only $OK_CHARS are allowed
$color =~ s/[^$OK_CHARS]/_/go;  # only $OK_CHARS are allowed

#$graph =~ s/\&/&amp;/g;
#$graph =~ s/\</&lt;/g;
#$graph =~ s/\>/&gt;/g;
#$graph =~ s/\"/&quot;/g;
#$graph =~ s/\'/&#x27;/g;
#$graph =~ s/\(/&#x28;/g;
#$graph =~ s/\)/&#x29;/g;
#$graph =~ s/\//&#x2F;/g;

if(lc($config{httpd_builtin}->{enabled}) ne "y") {
  print("Content-Type: text/html\n");
  print("\n");
}

# get the current OS and kernel version
my $release;
($config{os}, undef, $release) = uname();
if(!($release =~ m/^(\d+)\.(\d+)/)) {
  die "FATAL: unable to get the kernel version.";
}
$config{kernel} = "$1.$2";

$colors{graph_colors} = ();

push(@{$colors{graph_colors}}, "--color=CANVAS#" . $config{theme}->{$color}->{canvas}) if defined($config{theme}->{$color}->{canvas});
push(@{$colors{graph_colors}}, "--color=BACK#"   . $config{theme}->{$color}->{back})   if defined($config{theme}->{$color}->{back});
push(@{$colors{graph_colors}}, "--color=FONT#"   . $config{theme}->{$color}->{font})   if defined($config{theme}->{$color}->{font});
push(@{$colors{graph_colors}}, "--color=MGRID#"  . $config{theme}->{$color}->{mgrid})  if defined($config{theme}->{$color}->{mgrid});
push(@{$colors{graph_colors}}, "--color=GRID#"   . $config{theme}->{$color}->{grid})   if defined($config{theme}->{$color}->{grid});
push(@{$colors{graph_colors}}, "--color=FRAME#"  . $config{theme}->{$color}->{frame})  if defined($config{theme}->{$color}->{frame});
push(@{$colors{graph_colors}}, "--color=ARROW#"  . $config{theme}->{$color}->{arrow})  if defined($config{theme}->{$color}->{arrow});
push(@{$colors{graph_colors}}, "--color=SHADEA#" . $config{theme}->{$color}->{shadea}) if defined($config{theme}->{$color}->{shadea});
push(@{$colors{graph_colors}}, "--color=SHADEB#" . $config{theme}->{$color}->{shadeb}) if defined($config{theme}->{$color}->{shadeb});
push(@{$colors{graph_colors}}, "--color=AXIS#"   . $config{theme}->{$color}->{axis})   if defined($config{theme}->{$color}->{axis});

$colors{warning_color} = "--color=CANVAS#880000";

$colors{bg_color} = $config{theme}->{$color}->{main_bg};
$colors{fg_color} = $config{theme}->{$color}->{main_fg};
$colors{title_bg_color} = $config{theme}->{$color}->{title_bg};
$colors{title_fg_color} = $config{theme}->{$color}->{title_fg};
$colors{graph_bg_color} = $config{theme}->{$color}->{graph_bg};
$colors{gap} = $config{theme}->{$color}->{gap};


($tf{twhen}) = ($when =~ m/^\d+(hour|day|week|month|year)$/);
($tf{nwhen} = $when) =~ s/$tf{twhen}// unless !$tf{twhen};
$tf{nwhen} = 1 unless $tf{nwhen};
$tf{twhen} = "day" unless $tf{twhen};
$tf{when} = $tf{nwhen} . $tf{twhen};

# toggle this to 1 if you want to maintain old (2.3-) Monitorix with Multihost
if($config{backwards_compat_old_multihost}) {
  $tf{when} = $tf{twhen};
}

# make sure that some options are correctly defined
if(!$config{global_zoom}) {
  $config{global_zoom} = 1;
}
if(!$config{image_format}) {
  $config{image_format} = "PNG";
}

our ($res, $tc, $tb, $ts);
if($tf{twhen} eq "day") {
  ($tf{res}, $tf{tc}, $tf{tb}, $tf{ts}) = (3600, 'h', 24, 1);
}
if($tf{twhen} eq "week") {
  ($tf{res}, $tf{tc}, $tf{tb}, $tf{ts}) = (108000, 'd', 7, 1);
}
if($tf{twhen} eq "month") {
  ($tf{res}, $tf{tc}, $tf{tb}, $tf{ts}) = (216000, 'd', 30, 1);
}
if($tf{twhen} eq "year") {
  ($tf{res}, $tf{tc}, $tf{tb}, $tf{ts}) = (5184000, 'd', 365, 1);
}


if($RRDs::VERSION > 1.2) {
  push(@version12, "--slope-mode");
  push(@version12, "--font=LEGEND:7:");
  push(@version12, "--font=TITLE:9:");
  push(@version12, "--font=UNIT:8:");
  if($RRDs::VERSION >= 1.3) {
    push(@version12, "--font=DEFAULT:0:Mono");
  }
  if($tf{twhen} eq "day") {
    push(@version12, "--x-grid=HOUR:1:HOUR:6:HOUR:6:0:%R");
  }
  push(@version12_small, "--font=TITLE:8:");
  push(@version12_small, "--font=UNIT:7:");
  if($RRDs::VERSION >= 1.3) {
    push(@version12_small, "--font=DEFAULT:0:Mono");
  }
}


my $title;
my $str;
my @output;

$title = $config{hostname};
$title =~ s/ /&nbsp;/g;
my $twhen = $tf{nwhen} > 1 ? "$tf{nwhen} $tf{twhen}" : $tf{twhen};
$twhen .= "s" if $tf{nwhen} > 1;


print("<!DOCTYPE html>\n");
print("<html>\n");
print("  <head>\n");
print("    <title>$config{title}</title>\n");
print("    <link rel='shortcut icon' href='" . $config{url} . "/" . $config{favicon} . "'>\n");
print("    <link href='" . $config{url} . "/css/" . $color . ".css' rel='stylesheet'>\n");
if($config{refresh_rate}) {
    print("    <meta http-equiv='Refresh' content='" . $config{refresh_rate} . "'>\n");
}
print("    <meta name='mobile-web-app-capable' content='yes' />\n");
print("    <meta name='mobile-web-app-status-bar-style' content='black' />\n");
print("  </head>\n");

my $logo = "/$config{logo_top}";


page_header($logo, $title, $twhen);

$cgi{colors} = \%colors;
$cgi{tf} = \%tf;
$cgi{version12} = \@version12;
$cgi{version12_small} = \@version12_small;
$cgi{graph} = $graph;
$cgi{when} = $when;
$cgi{color} = $color;
$cgi{val} = $val;
$cgi{silent} = $silent;

  my %outputs;  # a hash of arrays
  my @readers;  # array of file descriptors
  my @writers;  # array of file descriptors
  my $children = 0;

  my $lockfile_handler = lockfile_handler(\%config) unless $ENV{INHIBIT_LOCKING};
  global_flock($lockfile_handler, LOCK_SH);
  foreach (split(',', $config{graph_name})) {
    my $gn = trim($_);
    my $g = "";
    if($graph ne "all") {
      ($g) = ($graph =~ m/^_*($gn)\d*$/);
      next unless $g;
    }
    if(lc($config{graph_enable}->{$gn}) eq "y") {
      my $cgi = $gn . "_cgi";

      eval "use $gn qw(" . $cgi . ")";
      if($@) {
        print(STDERR "WARNING: unable to load module '$gn. $@'\n");
        next;
      }

      if($graph eq "all" || $gn eq $g) {
        no strict "refs";

        if(lc($config{enable_parallelizing} || "") eq "y") {
          pipe($readers[$children], $writers[$children]);
          $writers[$children]->autoflush(1);

          if(!fork()) {
            my $child;

            close($readers[$children]);

            pipe(CHILD_RDR, PARENT_WTR);
            PARENT_WTR->autoflush(1);

            if(!($child = fork())) {
              # child
              my @output;
              close(CHILD_RDR);
              @output = &$cgi($gn, \%config, \%cgi);
              print(PARENT_WTR @output);
              close(PARENT_WTR);
              exit(0);
            }

            # parent
            my @output;
            close(PARENT_WTR);
            @output = <CHILD_RDR>;
            close(CHILD_RDR);
            waitpid($child, 0);
            my $fd = $writers[$children];
            print($fd @output);
            close($writers[$children]);
            exit(0);
          }
          close($writers[$children]);
          $children++;

        } else {
          my @output = &$cgi($gn, \%config, \%cgi);
          print @output;
        }
      }
    }
  }
  if(lc($config{enable_parallelizing} || "") eq "y") {
    my $n;
    my @output;

    for($n = 0; $n < $children; $n++) {
      my $fd = $readers[$n];
      @output = <$fd>;
      close($readers[$n]);
      @{$outputs{$n}} = @output;
      waitpid(-1, 0);  # wait for each child
      print @{$outputs{$n}} if $outputs{$n};
    }
  }
  global_flock($lockfile_handler, LOCK_UN);

page_footer();

0;
