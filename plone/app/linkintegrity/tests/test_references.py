from zope.component import adapts, getGlobalSiteManager
from zope.interface import implements
from Products.PloneTestCase import PloneTestCase
from Products.Archetypes.interfaces import IBaseObject
from plone.app.linkintegrity.interfaces import IReferencesUpdater
from plone.app.linkintegrity.tests.utils import getBrowser


PloneTestCase.setupPloneSite()


class ReferenceReferences(object):
    adapts(IBaseObject)
    implements(IReferencesUpdater)

    def __init__(self, context):
        self.context = context

    def update(self, refs):
        import pdb; pdb.set_trace( )
        refs['hurz!'] = set(self.context.getReferences(relationship='hurz!'))


class ReferenceGenerationTests(PloneTestCase.FunctionalTestCase):

    def testRelativeUpwardsLinkGeneratesMatchingReference(self):
        self.setRoles(['Manager'])
        portal = self.portal
        portal.invokeFactory('Document', id='foo', text='main foo!')
        folder = portal[portal.invokeFactory('Folder', id='folder')]
        folder.invokeFactory('Document', id='foo', text='sub foo?')
        doc = folder[folder.invokeFactory('Document', id='doc',
            text='<html> <body> <a href="../foo">go!</a> </body> </html>')]
        # the way relative links work it leads to the main 'foo'...
        browser = getBrowser(loggedIn=True)
        browser.open(doc.absolute_url())
        browser.getLink('go!').click()
        self.assertTrue('main foo' in browser.contents)
        # the internal reference should do the same...
        self.assertEqual(doc.getReferences(), [portal.foo])

    def testRelativeSiblingFolderLinkGeneratesMatchingReference(self):
        self.setRoles(['Manager'])
        portal = self.portal
        main = portal[portal.invokeFactory('Folder', id='main')]
        foo = main[main.invokeFactory('Folder', id='foo')]
        foo.invokeFactory('Document', id='doc', text='dox rule!')
        bar = main[main.invokeFactory('Folder', id='bar')]
        doc = bar[bar.invokeFactory('Document', id='doc',
            text='<html> <body> <a href="../foo/doc">go!</a> </body> </html>')]
        # the way relative links work it leads to the document in folder 'foo'
        browser = getBrowser(loggedIn=True)
        browser.open(doc.absolute_url())
        browser.getLink('go!').click()
        self.assertTrue('dox rule' in browser.contents)
        # the internal reference should do the same...
        self.assertEqual(doc.getReferences(), [portal.main.foo.doc])

    def testAdditionalReferencesCanBeCreatedViaSubscribers(self):
        self.setRoles(['Manager'])
        foo = self.portal[self.portal.invokeFactory('Document', id='foo')]
        bar = self.portal[self.portal.invokeFactory('Document', id='bar')]
        # let's assume we have a subscription adapter treating references
        # to be important with regard to content integrity...
        gsm = getGlobalSiteManager()
        gsm.registerSubscriptionAdapter(ReferenceReferences)
        # now we create a reference & try to delete the originating document...
        foo.addReference(bar, relationship='hurz!')
        foo.processForm()           # trigger update of integrity references...
        browser = getBrowser(loggedIn=True)
        browser.open(foo.absolute_url())
        browser.getLink('Delete').click()
        import pdb; pdb.set_trace( )
        self.assertTrue('Do you really want to delete this item?' in browser.contents)


    def testReferencesToNonAccessibleContentAreGenerated(self):
        self.loginAsPortalOwner()
        secret = self.portal[self.portal.invokeFactory('Document', id='secret')]
        self.login()
        # somebody created a document to which the user has no access...
        checkPermission = self.portal.portal_membership.checkPermission
        self.failIf(checkPermission('View', secret))
        self.failIf(checkPermission('Access contents information', secret))
        # nevertheless it should be possible to set a link to it...
        self.folder.invokeFactory('Document', id='doc',
            text='<html> <body> <a href="%s">go!</a> </body> </html>' %
            secret.absolute_url())
        self.assertEqual(self.folder.doc.getReferences(), [secret])
