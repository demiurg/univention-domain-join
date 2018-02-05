import logging
import os
import time

from univention_domain_join.join_steps.dns_configurator import DnsConfigurator
from univention_domain_join.join_steps.kerberos_configurator import KerberosConfigurator
from univention_domain_join.join_steps.ldap_configurator import LdapConfigurator
from univention_domain_join.join_steps.login_manager_configurator import LoginManagerConfigurator
from univention_domain_join.join_steps.pam_configurator import PamConfigurator
from univention_domain_join.join_steps.sssd_configurator import SssdConfigurator
from univention_domain_join.join_steps.utils import execute_as_root

userinfo_logger = logging.getLogger('userinfo')


class DomainJoinException(Exception):
	pass


class Joiner(object):
	def __init__(self, masters_ucr_variables, master_ip, master_username, master_pw, skip_login_manager):
		self.master_username = master_username
		self.master_pw = master_pw
		self.master_ip = master_ip
		self.skip_login_manager = skip_login_manager
		self.domain = masters_ucr_variables['domainname']
		self.nameservers = [
			masters_ucr_variables['nameserver1'] if masters_ucr_variables['nameserver1'] != "''" else '',
			masters_ucr_variables['nameserver2'] if masters_ucr_variables['nameserver2'] != "''" else '',
			masters_ucr_variables['nameserver3'] if masters_ucr_variables['nameserver3'] != "''" else ''
		]
		self.ldap_master = masters_ucr_variables['ldap_master']
		self.ldap_base = masters_ucr_variables['ldap_base']
		self.kerberos_realm = masters_ucr_variables['kerberos_realm']

	def check_if_join_is_possible_without_problems(self):
		if not self.skip_login_manager and LoginManagerConfigurator().configuration_conflicts():
			userinfo_logger.critical(
				'Joining the UCS domain is not safely possible.\n'
				'Please resolve all problems and run this tool again.'
			)
			raise DomainJoinException()

	def create_backup_of_config_files(self):
		backup_dir = self.create_backup_dir()

		DnsConfigurator(self.nameservers, self.domain).backup(backup_dir)
		LdapConfigurator().backup(backup_dir)
		SssdConfigurator().backup(backup_dir)
		PamConfigurator().backup(backup_dir)
		if not self.skip_login_manager:
			LoginManagerConfigurator().backup(backup_dir)
		KerberosConfigurator().backup(backup_dir)

		userinfo_logger.info('Created a backup of all configuration files, that will be modified at \'%s\'.' % backup_dir)

	@execute_as_root
	def create_backup_dir(self):
		backup_dir = os.path.join('/var/univention-backup', time.strftime("%Y%m%d%H%M%S_domain-join", time.gmtime()))
		os.makedirs(backup_dir)
		return backup_dir

	def join_domain(self):
		DnsConfigurator(self.nameservers, self.domain).configure_dns()
		LdapConfigurator().configure_ldap(self.ldap_master, self.master_username, self.master_pw, self.ldap_base)
		SssdConfigurator().setup_sssd(self.master_ip, self.ldap_master, self.ldap_base, self.kerberos_realm)
		PamConfigurator().setup_pam()
		if not self.skip_login_manager:
			LoginManagerConfigurator().enable_login_with_foreign_usernames()
		KerberosConfigurator().configure_kerberos(self.kerberos_realm, self.master_ip, self.ldap_master)
		# TODO: Stop avahi service to prevent problems with sssd?
		userinfo_logger.info('The domain join was successful.')
		userinfo_logger.info('Please reboot the system.')